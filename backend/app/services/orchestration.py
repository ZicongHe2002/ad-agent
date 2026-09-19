from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import QualityEvaluator, RiskAgent
from app.agents.factory import build_llm_provider
from app.api.utils import model_dict
from app.core.clock import utc_now
from app.domain.enums import (
    AuthStatus,
    CandidateStatus,
    CapabilityName,
    CapabilityStatus,
    ClaimStatus,
    CommentJobState,
    ContentProvenance,
    DisclosureStatus,
    PublishMode,
    QualityDecision,
    RankConfidence,
    ReviewStatus,
    RiskDecision,
)
from app.domain.state_machine import transition
from app.models import (
    AccountIdentityProfile,
    Brand,
    BrandAccount,
    Campaign,
    CommentCandidate,
    CommentJob,
    CommentQualityEvaluation,
    Creator,
    CreatorPlatformAccount,
    Post,
    PostAnchor,
    PostContent,
    Product,
    ProductClaim,
    PublishedComment,
    PublishJob,
    ReviewJob,
    RiskEvent,
    TimelineEvent,
    VoiceProfile,
)
from app.observability.metrics import record_job_state
from app.observability.tracing import current_trace_id
from app.repositories.outbox import OutboxRepository
from app.services.audit_service import write_audit_log
from app.services.capability_service import (
    CapabilityDecision,
    authorize_capability,
    capture_capability_snapshot,
)
from app.services.comment_service import merge_recent_comments, normalize_comment
from app.services.publish_service import build_idempotency_key, route_publish
from app.services.review_service import normalized_edit_distance, validate_review_text

_RESOLVED_DISCLOSURE_STATUSES = frozenset(
    {
        DisclosureStatus.NOT_REQUIRED,
        DisclosureStatus.DECLARED,
        DisclosureStatus.PLATFORM_APPLIED,
    }
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _account_scopes(account: BrandAccount) -> list[str]:
    metadata = account.credential_metadata or {}
    raw = metadata.get("scopes", metadata.get("granted_scopes", []))
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []
    return [str(item) for item in raw]


def _coerce_disclosure_status(value: DisclosureStatus | str | None) -> DisclosureStatus | None:
    if value is None:
        return None
    if isinstance(value, DisclosureStatus):
        return value
    try:
        return DisclosureStatus(str(value).upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_DISCLOSURE_STATUS"},
        ) from exc


def _validated_disclosure_resolution(
    candidate: CommentCandidate,
    identity: AccountIdentityProfile,
    *,
    requested_status: DisclosureStatus | str | None,
    evidence: dict[str, Any] | None,
) -> tuple[DisclosureStatus, dict[str, Any], bool]:
    """Validate a disclosure decision without mutating the candidate."""

    supplied = _coerce_disclosure_status(requested_status)
    unresolved = candidate.disclosure_status in {
        DisclosureStatus.REQUIRED_PENDING,
        DisclosureStatus.UNKNOWN,
    }
    policy_decision_required = bool(
        identity.requires_brand_disclosure
        or identity.requires_ai_disclosure_policy_check
    )
    if supplied is None:
        if unresolved or (
            policy_decision_required
            and (
                not candidate.disclosure_evidence
                or candidate.disclosure_resolved_at is None
            )
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "DISCLOSURE_RESOLUTION_REQUIRED",
                    "allowed_statuses": sorted(
                        item.value for item in _RESOLVED_DISCLOSURE_STATUSES
                    ),
                },
            )
        return candidate.disclosure_status, dict(candidate.disclosure_evidence or {}), False
    if supplied not in _RESOLVED_DISCLOSURE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={"code": "DISCLOSURE_STATUS_MUST_BE_RESOLVED"},
        )
    if not evidence:
        raise HTTPException(
            status_code=422,
            detail={"code": "DISCLOSURE_EVIDENCE_REQUIRED"},
        )
    if identity.requires_brand_disclosure and supplied == DisclosureStatus.NOT_REQUIRED:
        raise HTTPException(
            status_code=422,
            detail={"code": "BRAND_DISCLOSURE_CANNOT_BE_WAIVED"},
        )
    return supplied, dict(evidence), True


def _disclosure_is_publishable(
    candidate: CommentCandidate,
    identity: AccountIdentityProfile,
) -> bool:
    if (candidate.disclosure_evidence or {}).get("method") == "automatic_comment_text":
        return _has_automatic_text_disclosure(candidate, identity)
    if candidate.disclosure_status in {
        DisclosureStatus.REQUIRED_PENDING,
        DisclosureStatus.UNKNOWN,
    }:
        return False
    if (
        identity.requires_brand_disclosure
        and candidate.disclosure_status == DisclosureStatus.NOT_REQUIRED
    ):
        return False
    if (
        identity.requires_brand_disclosure
        or identity.requires_ai_disclosure_policy_check
    ):
        return bool(candidate.disclosure_evidence) and candidate.disclosure_resolved_at is not None
    return True


def automatic_disclosure_prefix(identity: AccountIdentityProfile) -> str:
    parts = []
    if identity.requires_brand_disclosure:
        parts.append(identity.public_identity_text.strip())
    if identity.requires_ai_disclosure_policy_check:
        parts.append("AI辅助生成")
    return f"【{'｜'.join(parts)}】" if parts else ""


def _has_automatic_text_disclosure(
    candidate: CommentCandidate, identity: AccountIdentityProfile,
) -> bool:
    """Verify disclosure in the actual outgoing text, never infer a platform label."""

    evidence = candidate.disclosure_evidence or {}
    prefix = automatic_disclosure_prefix(identity)
    return bool(
        prefix
        and candidate.disclosure_status == DisclosureStatus.DECLARED
        and candidate.disclosure_resolved_at is not None
        and evidence.get("method") == "automatic_comment_text"
        and evidence.get("identity_profile_id") == str(identity.id)
        and evidence.get("prefix") == prefix
        and candidate.text.startswith(prefix)
    )


async def publish_capability_decision(
    session: AsyncSession,
    *,
    post: Post,
    account: BrandAccount,
    capability: CapabilityName,
) -> CapabilityDecision:
    creator_account = await session.scalar(
        select(CreatorPlatformAccount).where(
            CreatorPlatformAccount.creator_id == post.creator_id,
            CreatorPlatformAccount.platform == post.platform,
        )
    )
    metadata = account.credential_metadata or {}
    return await authorize_capability(
        session,
        post.platform,
        capability,
        account_type=account.account_kind.value,
        target_content_type="VIDEO",
        has_authorization=account.auth_status == AuthStatus.VALID,
        granted_scopes=_account_scopes(account),
        external_creator_id=(
            creator_account.external_creator_id if creator_account is not None else None
        ),
        conditions_satisfied=bool(metadata.get("capability_conditions_satisfied", False)),
    )


async def write_timeline(
    session: AsyncSession,
    *,
    job: CommentJob | None,
    event_type: str,
    aggregate_id: UUID,
    aggregate_type: str = "Post",
    payload: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        comment_job_id=job.id if job else None,
        trace_id=job.trace_id if job else current_trace_id(),
        payload=payload or {},
        occurred_at=utc_now(),
    )
    session.add(event)
    await session.flush()
    return event


async def transition_job(
    session: AsyncSession,
    job: CommentJob,
    target: CommentJobState,
    reason: str,
) -> None:
    transition(job, target, reason)
    record_job_state(target.value)
    if target in {
        CommentJobState.PUBLISHED,
        CommentJobState.SKIPPED,
        CommentJobState.BLOCKED,
        CommentJobState.FAILED,
    }:
        job.finished_at = utc_now()
    await write_timeline(
        session,
        job=job,
        event_type=f"job.{target.value.lower()}",
        aggregate_id=job.post_id,
        payload={"state": target.value, "reason": reason, "state_version": job.state_version},
    )


async def ensure_publish_job(
    session: AsyncSession,
    comment_job: CommentJob,
    candidate: CommentCandidate,
    *,
    human_approved: bool = False,
) -> PublishJob:
    account = await session.get(BrandAccount, comment_job.brand_account_id)
    campaign = await session.get(Campaign, comment_job.campaign_id)
    post = await session.get(Post, comment_job.post_id)
    if account is None or campaign is None or post is None:
        raise RuntimeError("publish context is incomplete")

    key = build_idempotency_key(
        tenant_id=str(comment_job.tenant_id or "default"),
        platform=post.platform.value,
        brand_account_id=str(account.id),
        external_post_id=post.external_post_id,
        campaign_id=str(campaign.id),
        intent_key=comment_job.intent_key,
    )
    existing = await session.scalar(select(PublishJob).where(PublishJob.idempotency_key == key))
    if existing:
        return existing

    top_level_decision = await publish_capability_decision(
        session,
        post=post,
        account=account,
        capability=CapabilityName.TOP_LEVEL_COMMENT,
    )
    capability_status = top_level_decision.status
    if not top_level_decision.allowed:
        capability_status = (
            CapabilityStatus.RATE_LIMITED.value
            if top_level_decision.status == CapabilityStatus.RATE_LIMITED.value
            else (
                CapabilityStatus.DISABLED.value
                if top_level_decision.status == CapabilityStatus.DISABLED.value
                else CapabilityStatus.MANUAL.value
            )
        )
    identity = await session.get(AccountIdentityProfile, account.identity_profile_id)
    voice = await session.get(VoiceProfile, account.voice_profile_id)
    if (
        identity is None
        or not identity.active
        or identity.account_kind != account.account_kind
        or voice is None
        or not voice.active
    ):
        raise HTTPException(status_code=409, detail="Publishing identity is unavailable")
    if not _disclosure_is_publishable(candidate, identity):
        raise HTTPException(
            status_code=409,
            detail={"code": "DISCLOSURE_NOT_READY_FOR_PUBLISH"},
        )
    ai_disclosure_decision: CapabilityDecision | None = None
    if identity.requires_ai_disclosure_policy_check:
        ai_disclosure_decision = await publish_capability_decision(
            session,
            post=post,
            account=account,
            capability=CapabilityName.AI_DISCLOSURE,
        )
        if not ai_disclosure_decision.allowed:
            # Lack of a verified platform disclosure mechanism is a manual route,
            # never permission to omit the disclosure or call an unverified API.
            capability_status = CapabilityStatus.MANUAL.value
    route = route_publish(
        capability_status,
        authorization_satisfies_conditions=top_level_decision.allowed,
        kill_switch=bool(account.publisher_kill_switch or campaign.publisher_kill_switch),
    )
    if route.mode == "BLOCKED":
        await transition_job(
            session, comment_job, CommentJobState.BLOCKED, route.reason or "BLOCKED"
        )
        raise HTTPException(status_code=409, detail=route.reason)
    if route.mode == "DEFERRED":
        mode = PublishMode.UNSUPPORTED
        state = CommentJobState.READY_FOR_RETRY
    elif route.mode == "UNSUPPORTED":
        mode = PublishMode.UNSUPPORTED
        state = CommentJobState.WAITING_MANUAL_PUBLISH
    elif route.mode == "MANUAL":
        mode = PublishMode.MANUAL
        state = CommentJobState.WAITING_MANUAL_PUBLISH
    else:
        mode = PublishMode(route.mode)
        state = CommentJobState.READY

    capability_snapshot = await capture_capability_snapshot(
        session,
        post.platform,
        tenant_id=comment_job.tenant_id,
    )
    publish = PublishJob(
        comment_job_id=comment_job.id,
        candidate_id=candidate.id,
        brand_account_id=account.id,
        capability_snapshot_id=capability_snapshot.id,
        platform=post.platform,
        mode=mode,
        idempotency_key=key,
        state=state,
        state_reason=route.reason,
        reconciliation_evidence={
            "capability_decision": {
                "top_level_comment": {
                    "allowed": top_level_decision.allowed,
                    "status": top_level_decision.status,
                    "reason": top_level_decision.reason,
                    "record_id": str(top_level_decision.record_id)
                    if top_level_decision.record_id
                    else None,
                },
                "ai_disclosure": (
                    {
                        "allowed": ai_disclosure_decision.allowed,
                        "status": ai_disclosure_decision.status,
                        "reason": ai_disclosure_decision.reason,
                        "record_id": str(ai_disclosure_decision.record_id)
                        if ai_disclosure_decision.record_id
                        else None,
                    }
                    if ai_disclosure_decision is not None
                    else None
                ),
            }
        },
        next_retry_at=(utc_now() + timedelta(seconds=route.retry_after_seconds or 60))
        if route.mode == "DEFERRED"
        else None,
    )
    session.add(publish)
    await session.flush()
    if state == CommentJobState.WAITING_MANUAL_PUBLISH:
        await transition_job(
            session,
            comment_job,
            CommentJobState.WAITING_MANUAL_PUBLISH,
            route.reason or "MANUAL_WORKFLOW",
        )
    elif state == CommentJobState.READY:
        outbox = OutboxRepository(session)
        await outbox.append(
            aggregate_type="PublishJob",
            aggregate_id=publish.id,
            event_type="comment.publish.requested",
            payload={"publish_job_id": str(publish.id)},
            trace_id=comment_job.trace_id,
            idempotency_key=f"publish-request:{publish.id}",
        )
    elif state == CommentJobState.READY_FOR_RETRY:
        await transition_job(
            session,
            comment_job,
            CommentJobState.READY_FOR_RETRY,
            route.reason or "RETRY_LATER",
        )
        outbox = OutboxRepository(session)
        await outbox.append(
            aggregate_type="PublishJob",
            aggregate_id=publish.id,
            event_type="comment.publish.requested",
            payload={
                "publish_job_id": str(publish.id),
                "delay_ms": int((route.retry_after_seconds or 60) * 1000),
            },
            trace_id=comment_job.trace_id,
            idempotency_key=f"publish-request:{publish.id}",
        )
    return publish


async def select_review_candidate(
    session: AsyncSession,
    review_job_id: UUID,
    candidate_id: UUID,
    reviewer_id: UUID,
) -> dict[str, Any]:
    """Select an eligible candidate while keeping the review lock and audit trail."""

    review = await session.scalar(
        select(ReviewJob).where(ReviewJob.id == review_job_id).with_for_update()
    )
    if review is None:
        raise LookupError(f"ReviewJob {review_job_id} was not found")
    if review.status != ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Review job has already been resolved")
    now = utc_now()
    if review.expires_at is not None and _aware(review.expires_at) <= now:
        raise HTTPException(status_code=410, detail={"code": "REVIEW_JOB_EXPIRED"})
    if review.assigned_to != reviewer_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "REVIEW_CLAIM_REQUIRED"},
        )
    current_candidate = await session.get(CommentCandidate, review.candidate_id)
    if current_candidate is None or current_candidate.comment_job_id is None:
        raise HTTPException(status_code=409, detail="Current review candidate is unavailable")
    job = await session.scalar(
        select(CommentJob)
        .where(CommentJob.id == current_candidate.comment_job_id)
        .with_for_update()
    )
    if job is None or job.state != CommentJobState.WAITING_REVIEW:
        raise HTTPException(status_code=409, detail="Pipeline job is not waiting for review")
    candidate = await session.scalar(
        select(CommentCandidate).where(
            CommentCandidate.id == candidate_id,
            CommentCandidate.comment_job_id == job.id,
        )
    )
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CANDIDATE_NOT_IN_REVIEW_JOB"},
        )
    quality = await session.scalar(
        select(CommentQualityEvaluation).where(
            CommentQualityEvaluation.candidate_id == candidate.id
        )
    )
    risk = await session.scalar(
        select(RiskEvent)
        .where(RiskEvent.candidate_id == candidate.id)
        .order_by(RiskEvent.created_at.desc())
        .limit(1)
    )
    if (
        candidate.status == CandidateStatus.BLOCKED
        or quality is None
        or quality.decision == QualityDecision.BLOCK
        or risk is None
        or risk.final_decision == RiskDecision.BLOCK
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "CANDIDATE_NOT_REVIEW_ELIGIBLE"},
        )
    if candidate.id == current_candidate.id:
        return {
            **model_dict(review),
            "candidate": model_dict(candidate),
        }

    before_candidate_id = current_candidate.id
    if current_candidate.status != CandidateStatus.BLOCKED:
        current_candidate.status = CandidateStatus.GENERATED
    candidate.status = CandidateStatus.SELECTED
    review.candidate_id = candidate.id
    review.original_candidate_text = candidate.text
    review.final_text = None
    review.edit_reason = None
    review.edit_distance = None
    job.selected_candidate_id = candidate.id
    await write_audit_log(
        session,
        action="review.select_candidate",
        resource_type="ReviewJob",
        resource_id=review.id,
        actor_type="USER",
        actor_id=reviewer_id,
        trace_id=job.trace_id,
        before={"candidate_id": str(before_candidate_id)},
        after={"candidate_id": str(candidate.id)},
    )
    await session.flush()
    await session.refresh(review)
    return {
        **model_dict(review),
        "candidate": model_dict(candidate),
    }


async def resolve_review(
    session: AsyncSession,
    review_job_id: UUID,
    reviewer_id: UUID,
    *,
    action: str,
    final_text: str | None = None,
    notes: str | None = None,
    disclosure_status: DisclosureStatus | str | None = None,
    disclosure_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review = await session.scalar(
        select(ReviewJob).where(ReviewJob.id == review_job_id).with_for_update()
    )
    if review is None:
        raise LookupError(f"ReviewJob {review_job_id} was not found")
    if review.status != ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Review job has already been resolved")
    now = utc_now()
    if review.expires_at is not None and _aware(review.expires_at) <= now:
        raise HTTPException(
            status_code=410,
            detail={"code": "REVIEW_JOB_EXPIRED", "expires_at": review.expires_at.isoformat()},
        )
    if review.assigned_to is not None and review.assigned_to != reviewer_id:
        raise HTTPException(status_code=409, detail="Review job is claimed by another reviewer")
    candidate = await session.get(CommentCandidate, review.candidate_id)
    if candidate is None or candidate.comment_job_id is None:
        raise RuntimeError("review candidate context is missing")
    job = await session.scalar(
        select(CommentJob).where(CommentJob.id == candidate.comment_job_id).with_for_update()
    )
    if job is None or job.state != CommentJobState.WAITING_REVIEW:
        raise HTTPException(status_code=409, detail="Pipeline job is not waiting for review")

    if action == "reject":
        review.status = ReviewStatus.REJECTED
        review.assigned_to = reviewer_id
        review.resolved_at = utc_now()
        review.review_notes = notes
        candidate.status = CandidateStatus.REJECTED
        await transition_job(session, job, CommentJobState.SKIPPED, "HUMAN_REJECTED")
        await write_audit_log(
            session,
            action="review.reject",
            resource_type="ReviewJob",
            resource_id=review.id,
            actor_type="USER",
            actor_id=reviewer_id,
            trace_id=job.trace_id,
            after={"notes": notes},
        )
        return model_dict(review)
    if action not in {"approve", "edit-and-approve"}:
        raise ValueError("unknown review action")

    proposed_source = final_text if action == "edit-and-approve" else candidate.text
    proposed = (proposed_source or "").strip()
    account = await session.get(BrandAccount, candidate.brand_account_id)
    identity = (
        await session.get(AccountIdentityProfile, account.identity_profile_id) if account else None
    )
    voice = await session.get(VoiceProfile, account.voice_profile_id) if account else None
    anchor_rows = (
        await session.scalars(select(PostAnchor).where(PostAnchor.post_id == candidate.post_id))
    ).all()
    errors = validate_review_text(
        proposed,
        anchors=[item.anchor_text for item in anchor_rows],
        forbidden_phrases=voice.forbidden_phrases if voice else (),
        brand_official=bool(identity and identity.account_kind.value == "BRAND_OFFICIAL"),
    )
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"code": "EDIT_FAILED_HARD_GATES", "reasons": errors},
        )

    quality = await session.scalar(
        select(CommentQualityEvaluation).where(
            CommentQualityEvaluation.candidate_id == candidate.id
        )
    )
    latest_risk = await session.scalar(
        select(RiskEvent)
        .where(RiskEvent.candidate_id == candidate.id)
        .order_by(RiskEvent.created_at.desc())
        .limit(1)
    )
    if quality and quality.decision == QualityDecision.BLOCK:
        raise HTTPException(status_code=409, detail="A hard quality block cannot be overridden")
    if latest_risk and latest_risk.final_decision == RiskDecision.BLOCK:
        raise HTTPException(status_code=409, detail="A hard risk block cannot be overridden")

    campaign = await session.get(Campaign, candidate.campaign_id)
    if (
        account is None
        or identity is None
        or voice is None
        or campaign is None
        or not identity.active
        or identity.account_kind != account.account_kind
        or not voice.active
    ):
        raise HTTPException(status_code=409, detail="Review context is incomplete")
    approved_claims = (
        await session.scalars(
            select(ProductClaim)
            .join(Product, Product.id == ProductClaim.product_id)
            .where(
                Product.brand_id == campaign.brand_id,
                Product.active.is_(True),
                ProductClaim.status == ClaimStatus.APPROVED,
                ProductClaim.active.is_(True),
                or_(ProductClaim.expires_at.is_(None), ProductClaim.expires_at > now),
            )
        )
    ).all()
    if candidate.referenced_claim_ids:
        try:
            prior_claim_ids = [UUID(str(item)) for item in candidate.referenced_claim_ids]
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_REFERENCED_CLAIM"},
            ) from exc
        prior_claims = (
            await session.scalars(select(ProductClaim).where(ProductClaim.id.in_(prior_claim_ids)))
        ).all()
        active_claim_ids = {item.id for item in approved_claims}
        stale_claims_still_present = [
            str(item.id)
            for item in prior_claims
            if item.id not in active_claim_ids
            and normalize_comment(item.claim_text) in normalize_comment(proposed)
        ]
        if stale_claims_still_present:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REFERENCED_CLAIM_NO_LONGER_APPROVED",
                    "claim_ids": stale_claims_still_present,
                },
            )
    candidate_history = (
        await session.scalars(
            select(CommentCandidate.text)
            .where(
                CommentCandidate.brand_account_id == candidate.brand_account_id,
                CommentCandidate.id != candidate.id,
            )
            .order_by(CommentCandidate.created_at.desc())
            .limit(100)
        )
    ).all()
    published_history = (
        await session.scalars(
            select(PublishedComment.final_text)
            .where(PublishedComment.brand_account_id == candidate.brand_account_id)
            .order_by(PublishedComment.published_at.desc())
            .limit(100)
        )
    ).all()
    post_content = await session.get(PostContent, candidate.post_id)
    post = await session.get(Post, candidate.post_id)
    creator = await session.get(Creator, post.creator_id) if post else None
    if post_content is None or creator is None:
        raise HTTPException(status_code=409, detail="Post review context is incomplete")
    referenced_anchor_ids = [
        str(item.id)
        for item in anchor_rows
        if normalize_comment(item.anchor_text) in normalize_comment(proposed)
    ]
    referenced_claim_ids = [
        str(item.id)
        for item in approved_claims
        if normalize_comment(item.claim_text) in normalize_comment(proposed)
    ]
    hard_recheck = QualityEvaluator().evaluate(
        {
            "comment": proposed,
            "referenced_anchor_ids": referenced_anchor_ids,
            "referenced_claim_ids": referenced_claim_ids,
            "uses_first_person_experience": False,
            "implies_consumer_identity": False,
        },
        post=model_dict(post_content),
        anchors=[model_dict(item) for item in anchor_rows],
        recent_comments=merge_recent_comments(candidate_history, published_history),
        approved_claims=[model_dict(item) for item in approved_claims],
        account_identity=model_dict(identity),
        voice_profile=model_dict(voice),
        disclosure_prefix=automatic_disclosure_prefix(identity),
    )
    if hard_recheck.decision in {QualityDecision.BLOCK, QualityDecision.REGENERATE}:
        raise HTTPException(
            status_code=422,
            detail={"code": "EDIT_FAILED_QUALITY_GATES", "reasons": hard_recheck.reasons},
        )
    resolved_disclosure, resolved_evidence, disclosure_changed = _validated_disclosure_resolution(
        candidate,
        identity,
        requested_status=disclosure_status,
        evidence=disclosure_evidence,
    )
    brand = await session.get(Brand, campaign.brand_id)
    brand_mentioned = bool(
        brand
        and normalize_comment(brand.name)
        and normalize_comment(brand.name) in normalize_comment(proposed)
    )
    risk_recheck = await RiskAgent(provider=build_llm_provider(job.run_mode)).evaluate(
        {
            "comment": proposed,
            "post": model_dict(post_content),
            "account_identity": model_dict(identity),
            "approved_claims": [model_dict(item) for item in approved_claims],
            "creator_relationship": creator.relationship_type.value,
            "brand_mentioned": brand_mentioned,
            "fake_experience": hard_recheck.fake_experience_detected,
            "fake_identity": hard_recheck.fake_identity_detected,
            "unapproved_claim": hard_recheck.unsupported_claim_detected,
            "external_contact": hard_recheck.external_contact_detected,
            "account_kill_switch": account.publisher_kill_switch,
            "campaign_kill_switch": campaign.publisher_kill_switch,
            "disclosure_unresolved": resolved_disclosure
            in {DisclosureStatus.REQUIRED_PENDING, DisclosureStatus.UNKNOWN},
            "uncertain_categories": [
                *(
                    ["GENERAL_CREATOR_BRAND_MENTION"]
                    if creator.relationship_type.value == "GENERAL_CREATOR" and brand_mentioned
                    else []
                ),
                *(["PRODUCT_CLAIM_PRESENT"] if referenced_claim_ids else []),
            ],
        }
    )
    if risk_recheck.decision == RiskDecision.BLOCK:
        raise HTTPException(
            status_code=422,
            detail={"code": "EDIT_FAILED_RISK_GATES", "reasons": risk_recheck.reasons},
        )

    original = candidate.text
    edited = proposed != original
    if edited:
        candidate.text = proposed
        candidate.normalized_text = normalize_comment(proposed)
        candidate.content_provenance = ContentProvenance.AI_ASSISTED_HUMAN_EDITED
    else:
        candidate.content_provenance = ContentProvenance.AI_GENERATED_HUMAN_APPROVED
    candidate.referenced_anchor_ids = referenced_anchor_ids
    candidate.referenced_claim_ids = referenced_claim_ids
    candidate.disclosure_status = resolved_disclosure
    if disclosure_changed:
        candidate.disclosure_evidence = resolved_evidence
        candidate.disclosure_resolved_at = now
        candidate.disclosure_resolved_by_user_id = reviewer_id
    candidate.status = CandidateStatus.SELECTED
    if quality:
        for field in (
            "anchor_coverage",
            "specificity",
            "fluency",
            "voice_match",
            "novelty",
            "truthfulness",
            "identity_consistency",
            "duplicate_similarity_max",
            "generic_praise_detected",
            "fake_experience_detected",
            "fake_identity_detected",
            "unsupported_claim_detected",
            "random_typo_pattern_detected",
            "quality_score",
        ):
            value = getattr(hard_recheck, field)
            if field == "quality_score":
                value = Decimal(str(value))
            setattr(quality, field, value)
        quality.decision = QualityDecision.ALLOW
        quality.reasons = list(
            dict.fromkeys([*quality.reasons, "HUMAN_APPROVED_AFTER_HARD_GATE_RECHECK"])
        )
    session.add(
        RiskEvent(
            candidate_id=candidate.id,
            rule_decision=risk_recheck.decision,
            llm_decision=None,
            final_decision=RiskDecision.ALLOW,
            risk_score=risk_recheck.risk_score,
            matched_rules=risk_recheck.matched_policy_categories,
            reasons=list(
                dict.fromkeys([*risk_recheck.reasons, "HUMAN_APPROVED_AFTER_HARD_GATE_RECHECK"])
            ),
            policy_versions={"review_hard_gates": "v1"},
            created_at=utc_now(),
        )
    )
    review.status = ReviewStatus.EDITED_APPROVED if edited else ReviewStatus.APPROVED
    review.assigned_to = reviewer_id
    review.resolved_at = utc_now()
    review.final_text = proposed
    review.review_notes = notes
    review.edit_reason = notes if edited else None
    review.edit_distance = (
        Decimal(str(normalized_edit_distance(original, proposed))) if edited else Decimal("0")
    )
    job.selected_candidate_id = candidate.id
    await transition_job(session, job, CommentJobState.READY, "HUMAN_APPROVED")
    publish = await ensure_publish_job(session, job, candidate, human_approved=True)
    await write_audit_log(
        session,
        action="review.edit_approve" if edited else "review.approve",
        resource_type="ReviewJob",
        resource_id=review.id,
        actor_type="USER",
        actor_id=reviewer_id,
        trace_id=job.trace_id,
        before={"candidate_text": original},
        after={
            "final_text": proposed,
            "publish_job_id": str(publish.id),
            "disclosure_status": candidate.disclosure_status.value,
            "disclosure_evidence": candidate.disclosure_evidence,
        },
    )
    await session.flush()
    await session.refresh(review)
    await session.refresh(publish)
    return {**model_dict(review), "publish_job": model_dict(publish)}


async def confirm_manual_publish(
    session: AsyncSession,
    publish_job_id: UUID,
    result: str,
    external_comment_id: str | None,
    *,
    operator_id: UUID | None = None,
    operator_confirmed: bool = False,
    disclosure_status: DisclosureStatus | str | None = None,
    disclosure_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    publish = await session.scalar(
        select(PublishJob).where(PublishJob.id == publish_job_id).with_for_update()
    )
    if publish is None:
        raise LookupError(f"PublishJob {publish_job_id} was not found")
    if publish.state != CommentJobState.WAITING_MANUAL_PUBLISH:
        raise HTTPException(status_code=409, detail="Publish job is not manual")
    candidate = await session.get(CommentCandidate, publish.candidate_id)
    job = await session.get(CommentJob, publish.comment_job_id) if publish.comment_job_id else None
    if candidate is None:
        raise RuntimeError("manual publish candidate is missing")
    account = await session.get(BrandAccount, candidate.brand_account_id)
    identity = (
        await session.get(AccountIdentityProfile, account.identity_profile_id) if account else None
    )
    if account is None or identity is None:
        raise RuntimeError("manual publish identity is missing")
    current = utc_now()
    if result == "published":
        voice = await session.get(VoiceProfile, account.voice_profile_id)
        if (
            not identity.active
            or identity.account_kind != account.account_kind
            or voice is None
            or not voice.active
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "PUBLISHING_IDENTITY_OR_VOICE_INACTIVE"},
            )
        if not operator_confirmed:
            raise HTTPException(
                status_code=422,
                detail={"code": "MANUAL_OPERATOR_CONFIRMATION_REQUIRED"},
            )
        resolved_disclosure, resolved_evidence, disclosure_changed = (
            _validated_disclosure_resolution(
                candidate,
                identity,
                requested_status=disclosure_status,
                evidence=disclosure_evidence,
            )
        )
        if disclosure_changed:
            if operator_id is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "DISCLOSURE_RESOLVER_REQUIRED"},
                )
            candidate.disclosure_status = resolved_disclosure
            candidate.disclosure_evidence = resolved_evidence
            candidate.disclosure_resolved_at = current
            candidate.disclosure_resolved_by_user_id = operator_id
        if not _disclosure_is_publishable(candidate, identity):
            raise HTTPException(
                status_code=422,
                detail={"code": "DISCLOSURE_NOT_READY_FOR_PUBLISH"},
            )
        transition(publish, CommentJobState.PUBLISHED, "MANUAL_CONFIRMED")
        publish.finished_at = current
        post = await session.get(Post, candidate.post_id)
        published = PublishedComment(
            publish_job_id=publish.id,
            post_id=candidate.post_id,
            campaign_id=candidate.campaign_id,
            creator_id=post.creator_id if post else None,
            brand_account_id=candidate.brand_account_id,
            platform=publish.platform,
            external_comment_id=external_comment_id,
            final_text=candidate.text,
            content_provenance=candidate.content_provenance,
            disclosure_status=candidate.disclosure_status,
            published_at=current,
            chronological_rank_confidence=RankConfidence.UNKNOWN,
            visible_rank_confidence=RankConfidence.UNKNOWN,
        )
        session.add(published)
        if job:
            await transition_job(session, job, CommentJobState.PUBLISHED, "MANUAL_CONFIRMED")
    elif result == "skipped":
        transition(publish, CommentJobState.SKIPPED, "MANUAL_SKIPPED")
        publish.finished_at = utc_now()
        if job:
            await transition_job(session, job, CommentJobState.SKIPPED, "MANUAL_SKIPPED")
    else:
        transition(publish, CommentJobState.FAILED, "MANUAL_FAILED")
        publish.finished_at = utc_now()
        if job:
            await transition_job(session, job, CommentJobState.FAILED, "MANUAL_FAILED")
    await write_audit_log(
        session,
        action=f"publish.manual_{result}",
        resource_type="PublishJob",
        resource_id=publish.id,
        actor_type="USER" if operator_id else "SYSTEM",
        actor_id=operator_id,
        trace_id=job.trace_id if job else current_trace_id(),
        after={
            "result": result,
            "external_comment_id": external_comment_id,
            "operator_confirmed": operator_confirmed,
            "disclosure_status": candidate.disclosure_status.value,
            "disclosure_evidence": candidate.disclosure_evidence,
        },
    )
    await session.flush()
    await session.refresh(publish)
    return model_dict(publish)
