from __future__ import annotations

from datetime import timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.domain.enums import (
    AuthStatus,
    BrandStatus,
    CampaignStatus,
    CapabilityName,
    CapabilityStatus,
    ClaimStatus,
    CommentJobState,
    DisclosureStatus,
    Platform,
    QualityDecision,
    RankConfidence,
    ReviewStatus,
    RiskDecision,
    TenantStatus,
)
from app.domain.state_machine import transition
from app.models import (
    AccountIdentityProfile,
    Brand,
    BrandAccount,
    Campaign,
    CapabilitySnapshot,
    CommentCandidate,
    CommentJob,
    CommentQualityEvaluation,
    Post,
    Product,
    ProductClaim,
    PublishedComment,
    PublishJob,
    ReviewJob,
    RiskEvent,
    Tenant,
    VoiceProfile,
)
from app.observability.metrics import PUBLISH_LATENCY, RANK_MEASUREMENT_TOTAL, record_publish
from app.observability.tracing import current_trace_id
from app.platforms.base import PublishCommentRequest, ReconcileRequest
from app.platforms.errors import (
    PlatformError,
    PlatformTemporaryError,
    map_platform_exception,
)
from app.platforms.runtime import runtime_registry
from app.services.audit_service import write_audit_log
from app.services.orchestration import (
    _disclosure_is_publishable,
    _has_automatic_text_disclosure,
    publish_capability_decision,
    transition_job,
    write_timeline,
)
from app.services.publish_retry_policy import (
    MAX_PUBLISH_ATTEMPTS,
    MAX_RECONCILE_ATTEMPTS,
    ensure_publish_attempt_allowed,
    finish_publish_job,
    reconciliation_attempts,
    retry_is_due,
)
from app.services.publishing_policy_service import load_publishing_policy


async def _context(
    session: AsyncSession,
    publish_id: UUID,
) -> tuple[PublishJob, CommentCandidate, CommentJob | None, BrandAccount, Campaign, Post]:
    publish = await session.scalar(
        select(PublishJob).where(PublishJob.id == publish_id).with_for_update()
    )
    if publish is None:
        raise LookupError(f"PublishJob {publish_id} was not found")
    candidate = await session.get(CommentCandidate, publish.candidate_id)
    if candidate is None:
        raise RuntimeError("Publish candidate is missing")
    comment_job = (
        await session.get(CommentJob, publish.comment_job_id) if publish.comment_job_id else None
    )
    # All jobs acquire account then campaign locks in this order.  Together with
    # active publish reservations below, this serializes the final daily-quota
    # check across distinct PublishJobs before any external side effect.
    account = await session.scalar(
        select(BrandAccount).where(BrandAccount.id == publish.brand_account_id).with_for_update()
    )
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == candidate.campaign_id).with_for_update()
    )
    post = await session.get(Post, candidate.post_id)
    if account is None or campaign is None or post is None:
        raise RuntimeError("Publish account, campaign, or post is missing")
    return publish, candidate, comment_job, account, campaign, post


async def _assert_publish_gates(
    session: AsyncSession,
    publish: PublishJob,
    candidate: CommentCandidate,
    account: BrandAccount,
    campaign: Campaign,
    post: Post,
) -> None:
    if publish.state not in {CommentJobState.READY, CommentJobState.READY_FOR_RETRY}:
        raise ValueError(f"Publish job is not ready: {publish.state.value}")
    if account.publisher_kill_switch or campaign.publisher_kill_switch:
        raise PermissionError("Kill switch is enabled")
    if campaign.status != CampaignStatus.ACTIVE:
        raise PermissionError("Campaign is not active")
    brand = await session.get(Brand, campaign.brand_id)
    if brand is None or brand.status != BrandStatus.ACTIVE:
        raise PermissionError("Publishing brand is not active")
    if brand.tenant_id is not None:
        tenant = await session.get(Tenant, brand.tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise PermissionError("Publishing tenant is not active")
    now = utc_now()
    if (
        campaign.start_at
        and campaign.start_at.replace(tzinfo=campaign.start_at.tzinfo or now.tzinfo) > now
    ):
        raise PermissionError("Campaign has not started")
    if (
        campaign.end_at
        and campaign.end_at.replace(tzinfo=campaign.end_at.tzinfo or now.tzinfo) <= now
    ):
        raise PermissionError("Campaign has ended")
    if account.auth_status != AuthStatus.VALID:
        raise PermissionError("Platform authorization is not valid")
    identity = await session.get(AccountIdentityProfile, account.identity_profile_id)
    if identity is None or not identity.active or identity.account_kind != account.account_kind:
        raise PermissionError("Publishing identity is missing, inactive, or inconsistent")
    voice = await session.get(VoiceProfile, account.voice_profile_id)
    if voice is None or not voice.active:
        raise PermissionError("Publishing voice profile is missing or inactive")
    snapshot = (
        await session.get(CapabilitySnapshot, publish.capability_snapshot_id)
        if publish.capability_snapshot_id
        else None
    )
    if snapshot is None:
        raise PermissionError("A capability snapshot is required before publishing")
    if snapshot.expires_at and snapshot.expires_at.replace(
        tzinfo=snapshot.expires_at.tzinfo or now.tzinfo
    ) <= now:
        raise PermissionError("Capability snapshot has expired")
    snap_status = CapabilityStatus(
        snapshot.capabilities.get(CapabilityName.TOP_LEVEL_COMMENT.value.lower(), "UNKNOWN")
    )
    if snap_status not in {CapabilityStatus.SUPPORTED, CapabilityStatus.CONDITIONAL}:
        raise PermissionError("Snapshot does not permit top-level publishing")
    top_level_decision = await publish_capability_decision(
        session,
        post=post,
        account=account,
        capability=CapabilityName.TOP_LEVEL_COMMENT,
    )
    if not top_level_decision.allowed:
        raise PermissionError(
            f"Current capability registry blocks top-level publishing: {top_level_decision.reason}"
        )
    if identity.requires_ai_disclosure_policy_check:
        ai_disclosure_decision = await publish_capability_decision(
            session,
            post=post,
            account=account,
            capability=CapabilityName.AI_DISCLOSURE,
        )
        if not ai_disclosure_decision.allowed:
            raise PermissionError(
                "Current capability registry does not verify AI disclosure: "
                f"{ai_disclosure_decision.reason}"
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
    if quality is None or quality.decision != QualityDecision.ALLOW:
        raise PermissionError("Quality gate did not allow publishing")
    if risk is None or risk.final_decision != RiskDecision.ALLOW:
        raise PermissionError("Risk gate did not allow publishing")
    review = await session.scalar(
        select(ReviewJob).where(
            ReviewJob.candidate_id == candidate.id,
            ReviewJob.status.in_([ReviewStatus.APPROVED, ReviewStatus.EDITED_APPROVED]),
        )
    )
    if review is None:
        policy = await load_publishing_policy(session, brand.tenant_id)
        if (
            policy.mode != "AUTO"
            or campaign.human_review_required
            or not account.auto_publish_enabled
        ):
            raise PermissionError("Auto publish is disabled and no human approval exists")
        if _has_automatic_text_disclosure(candidate, identity) and not policy.auto_disclosure_enabled:
            raise PermissionError("Automatic disclosure is disabled and no human approval exists")
    if (
        identity.requires_ai_disclosure_policy_check
        and review is None
        and not _has_automatic_text_disclosure(candidate, identity)
    ):
        raise PermissionError("AI disclosure policy check requires human approval")
    if candidate.disclosure_status in {
        DisclosureStatus.REQUIRED_PENDING,
        DisclosureStatus.UNKNOWN,
    }:
        raise PermissionError("Disclosure status is unresolved")
    if not _disclosure_is_publishable(candidate, identity):
        raise PermissionError("Disclosure evidence is missing or inconsistent")
    if candidate.referenced_claim_ids:
        try:
            referenced_claim_ids = [UUID(str(item)) for item in candidate.referenced_claim_ids]
        except (TypeError, ValueError) as exc:
            raise PermissionError("Candidate contains an invalid claim reference") from exc
        valid_claim_count = await session.scalar(
            select(func.count())
            .select_from(ProductClaim)
            .join(Product, Product.id == ProductClaim.product_id)
            .where(
                ProductClaim.id.in_(referenced_claim_ids),
                Product.brand_id == campaign.brand_id,
                Product.active.is_(True),
                ProductClaim.status == ClaimStatus.APPROVED,
                ProductClaim.active.is_(True),
                or_(ProductClaim.expires_at.is_(None), ProductClaim.expires_at > now),
            )
        )
        if int(valid_claim_count or 0) != len(set(referenced_claim_ids)):
            raise PermissionError("A referenced product claim is no longer approved")
    day_start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    reserved_states = {
        CommentJobState.PUBLISHING,
        CommentJobState.PUBLISH_UNCERTAIN,
    }
    published_today = await session.scalar(
        select(func.count())
        .select_from(PublishedComment)
        .where(
            PublishedComment.brand_account_id == account.id,
            PublishedComment.published_at >= day_start,
            PublishedComment.published_at < day_end,
        )
    )
    account_reservations = await session.scalar(
        select(func.count())
        .select_from(PublishJob)
        .where(
            PublishJob.brand_account_id == account.id,
            PublishJob.id != publish.id,
            PublishJob.state.in_(reserved_states),
            PublishJob.started_at.is_not(None),
            PublishJob.started_at >= day_start,
            PublishJob.started_at < day_end,
        )
    )
    if int(published_today or 0) + int(account_reservations or 0) >= account.max_comments_per_day:
        raise PermissionError("Account daily limit exceeded")
    campaign_today = await session.scalar(
        select(func.count())
        .select_from(PublishedComment)
        .where(
            PublishedComment.campaign_id == campaign.id,
            PublishedComment.published_at >= day_start,
            PublishedComment.published_at < day_end,
        )
    )
    campaign_reservations = await session.scalar(
        select(func.count())
        .select_from(PublishJob)
        .join(CommentCandidate, CommentCandidate.id == PublishJob.candidate_id)
        .where(
            CommentCandidate.campaign_id == campaign.id,
            PublishJob.id != publish.id,
            PublishJob.state.in_(reserved_states),
            PublishJob.started_at.is_not(None),
            PublishJob.started_at >= day_start,
            PublishJob.started_at < day_end,
        )
    )
    if int(campaign_today or 0) + int(campaign_reservations or 0) >= campaign.max_comments_per_day:
        raise PermissionError("Campaign daily limit exceeded")
    creator_today = await session.scalar(
        select(func.count())
        .select_from(PublishedComment)
        .where(
            PublishedComment.campaign_id == campaign.id,
            PublishedComment.creator_id == post.creator_id,
            PublishedComment.published_at >= day_start,
            PublishedComment.published_at < day_end,
        )
    )
    creator_reservations = await session.scalar(
        select(func.count())
        .select_from(PublishJob)
        .join(CommentCandidate, CommentCandidate.id == PublishJob.candidate_id)
        .join(Post, Post.id == CommentCandidate.post_id)
        .where(
            CommentCandidate.campaign_id == campaign.id,
            Post.creator_id == post.creator_id,
            PublishJob.id != publish.id,
            PublishJob.state.in_(reserved_states),
            PublishJob.started_at.is_not(None),
            PublishJob.started_at >= day_start,
            PublishJob.started_at < day_end,
        )
    )
    if (
        int(creator_today or 0) + int(creator_reservations or 0)
        >= campaign.max_comments_per_creator_per_day
    ):
        raise PermissionError("Creator daily limit exceeded")


async def _record_external_failure(
    session: AsyncSession,
    *,
    publish: PublishJob,
    comment_job: CommentJob | None,
    post: Post,
    error: PlatformError,
) -> None:
    """Persist the outcome of a failed external call before the actor returns.

    Once an external request has started, retryable transport failures are
    treated as uncertain until reconciliation proves that no comment exists.
    This avoids duplicate publishing after a timeout or worker crash.
    """

    info = map_platform_exception(error)
    uncertain = info.retryable
    target = CommentJobState.PUBLISH_UNCERTAIN if uncertain else CommentJobState.FAILED
    reason = "PLATFORM_OUTCOME_UNCERTAIN" if uncertain else "PLATFORM_REJECTED"
    transition(publish, target, reason)
    publish.last_error_code = info.code
    publish.last_error_message = info.message[:2000]
    if uncertain:
        retry_after = info.details.get("retry_after")
        delay_seconds = (
            float(retry_after)
            if isinstance(retry_after, (int, float))
            else float(min(60, 2**publish.attempt_count))
        )
        delay_seconds = max(
            1.0,
            delay_seconds,
        )
        publish.next_retry_at = utc_now() + timedelta(seconds=delay_seconds)
    else:
        publish.finished_at = utc_now()
        publish.next_retry_at = None
    if comment_job:
        await transition_job(session, comment_job, target, reason)
    record_publish(publish.platform.value, "uncertain" if uncertain else "failed")
    await write_timeline(
        session,
        job=comment_job,
        event_type="comment.publish.uncertain" if uncertain else "comment.publish.failed",
        aggregate_id=post.id,
        payload={
            "publish_job_id": str(publish.id),
            "error_code": info.code,
            "retryable": info.retryable,
            "attempt": publish.attempt_count,
        },
    )
    await write_audit_log(
        session,
        action="publish.uncertain" if uncertain else "publish.failed",
        resource_type="PublishJob",
        resource_id=publish.id,
        actor_type="WORKER",
        trace_id=comment_job.trace_id if comment_job else current_trace_id(),
        after={
            "error_code": info.code,
            "retryable": info.retryable,
            "attempt": publish.attempt_count,
        },
    )
    await session.flush()


async def publish_comment_job(session: AsyncSession, publish_id: UUID) -> PublishedComment:
    publish, candidate, comment_job, account, campaign, post = await _context(session, publish_id)
    existing = await session.scalar(
        select(PublishedComment).where(PublishedComment.publish_job_id == publish.id)
    )
    if existing:
        return existing
    await ensure_publish_attempt_allowed(session, publish)
    await _assert_publish_gates(session, publish, candidate, account, campaign, post)
    if publish.mode.value not in {"OFFICIAL_API", "OFFICIAL_PARTNER"}:
        raise PermissionError("Publish job is not routed to an official capability")

    transition(publish, CommentJobState.PUBLISHING, "EXTERNAL_CALL_START")
    publish.attempt_count += 1
    publish.started_at = utc_now()
    publish_started_at = publish.started_at
    if comment_job and comment_job.state in {
        CommentJobState.READY,
        CommentJobState.READY_FOR_RETRY,
    }:
        await transition_job(
            session, comment_job, CommentJobState.PUBLISHING, "EXTERNAL_CALL_START"
        )
    # Make the intent durable before the external side effect. Reconciliation can
    # now recover even if the worker dies after the platform accepts the comment.
    await session.commit()

    adapter = runtime_registry.get(publish.platform)
    request = PublishCommentRequest(
        external_post_id=post.external_post_id,
        text=candidate.text,
        account_id=str(account.id),
        idempotency_key=publish.idempotency_key,
        disclosure=(
            candidate.disclosure_status.value
            if candidate.disclosure_status != DisclosureStatus.NOT_REQUIRED
            else None
        ),
    )
    try:
        receipt = await adapter.publish_top_level_comment(request)
    except PlatformError as exc:
        await _record_external_failure(
            session,
            publish=publish,
            comment_job=comment_job,
            post=post,
            error=exc,
        )
        raise
    except Exception as exc:
        # Do not persist or return arbitrary SDK exception text because it can
        # contain credentials. Convert it to the stable, redacted error surface.
        normalized = PlatformTemporaryError(
            "Unexpected platform integration failure",
            platform=publish.platform.value,
            details={"operation": "publish_top_level_comment"},
        )
        await _record_external_failure(
            session,
            publish=publish,
            comment_job=comment_job,
            post=post,
            error=normalized,
        )
        raise normalized from exc

    chronological_rank = None
    visible_rank = None
    if publish.platform == Platform.MOCK and hasattr(adapter, "service"):
        chronological_rank, visible_rank = await adapter.service.comment_ranks(
            post.external_post_id, receipt.external_comment_id
        )
    published = PublishedComment(
        publish_job_id=publish.id,
        post_id=post.id,
        campaign_id=campaign.id,
        creator_id=post.creator_id,
        brand_account_id=account.id,
        platform=publish.platform,
        external_comment_id=receipt.external_comment_id,
        final_text=candidate.text,
        content_provenance=candidate.content_provenance,
        disclosure_status=candidate.disclosure_status,
        published_at=receipt.created_at,
        chronological_rank=chronological_rank,
        chronological_rank_confidence=RankConfidence.EXACT
        if chronological_rank
        else RankConfidence.UNKNOWN,
        visible_rank=visible_rank,
        visible_rank_confidence=RankConfidence.EXACT if visible_rank else RankConfidence.UNKNOWN,
        rank_observed_at=utc_now() if chronological_rank else None,
    )
    session.add(published)
    record_publish(publish.platform.value, "success")
    if publish_started_at:
        PUBLISH_LATENCY.observe(max(0.0, (utc_now() - publish_started_at).total_seconds()))
    RANK_MEASUREMENT_TOTAL.labels(
        type="chronological",
        confidence=(RankConfidence.EXACT if chronological_rank else RankConfidence.UNKNOWN).value,
    ).inc()
    RANK_MEASUREMENT_TOTAL.labels(
        type="visible",
        confidence=(RankConfidence.EXACT if visible_rank else RankConfidence.UNKNOWN).value,
    ).inc()
    transition(publish, CommentJobState.PUBLISHED, "PLATFORM_CONFIRMED")
    publish.finished_at = utc_now()
    publish.next_retry_at = None
    publish.external_request_id = receipt.external_comment_id
    if comment_job:
        await transition_job(session, comment_job, CommentJobState.PUBLISHED, "PLATFORM_CONFIRMED")
    await write_timeline(
        session,
        job=comment_job,
        event_type="comment.published",
        aggregate_id=post.id,
        payload={
            "external_comment_id": receipt.external_comment_id,
            "chronological_rank": chronological_rank,
            "visible_rank": visible_rank,
        },
    )
    await write_audit_log(
        session,
        action="publish.succeeded",
        resource_type="PublishJob",
        resource_id=publish.id,
        actor_type="WORKER",
        trace_id=comment_job.trace_id if comment_job else current_trace_id(),
        after={
            "external_comment_id": receipt.external_comment_id,
            "chronological_rank": chronological_rank,
            "visible_rank": visible_rank,
        },
    )
    await session.flush()
    return published


async def reconcile_publish_job(session: AsyncSession, publish_id: UUID) -> PublishJob:
    publish, candidate, comment_job, account, _campaign, post = await _context(session, publish_id)
    if publish.state != CommentJobState.PUBLISH_UNCERTAIN:
        return publish
    attempts = reconciliation_attempts(publish)
    if attempts >= MAX_RECONCILE_ATTEMPTS:
        await finish_publish_job(session, publish, "RECONCILIATION_ATTEMPTS_EXHAUSTED")
        return publish
    if not retry_is_due(publish):
        return publish
    publish.reconciliation_evidence = {
        **dict(publish.reconciliation_evidence or {}),
        "reconcile_publish_attempt": publish.attempt_count,
        "reconcile_attempt_count": attempts + 1,
    }
    publish.next_retry_at = utc_now() + timedelta(seconds=min(60, 2 ** (attempts + 1)))
    # Persist the read attempt before the platform call, including when a worker
    # crashes or an SDK exception makes the actor roll back its later work.
    await session.commit()
    adapter = runtime_registry.get(publish.platform)
    result = await adapter.reconcile_publish(
        ReconcileRequest(
            external_post_id=post.external_post_id,
            account_id=str(account.id),
            idempotency_key=publish.idempotency_key,
        )
    )
    if result.found and result.receipt:
        receipt = result.receipt
        chronological_rank = None
        visible_rank = None
        if publish.platform == Platform.MOCK and hasattr(adapter, "service"):
            chronological_rank, visible_rank = await adapter.service.comment_ranks(
                post.external_post_id, receipt.external_comment_id
            )
        existing = PublishedComment(
            publish_job_id=publish.id,
            post_id=post.id,
            campaign_id=candidate.campaign_id,
            creator_id=post.creator_id,
            brand_account_id=account.id,
            platform=publish.platform,
            external_comment_id=receipt.external_comment_id,
            final_text=candidate.text,
            content_provenance=candidate.content_provenance,
            disclosure_status=candidate.disclosure_status,
            published_at=receipt.created_at,
            chronological_rank=chronological_rank,
            chronological_rank_confidence=(
                RankConfidence.EXACT if chronological_rank else RankConfidence.UNKNOWN
            ),
            visible_rank=visible_rank,
            visible_rank_confidence=(
                RankConfidence.EXACT if visible_rank else RankConfidence.UNKNOWN
            ),
            rank_observed_at=utc_now() if chronological_rank else None,
        )
        session.add(existing)
        transition(publish, CommentJobState.PUBLISHED, "RECONCILED_PUBLISHED")
        publish.finished_at = utc_now()
        publish.next_retry_at = None
        publish.external_request_id = receipt.external_comment_id
        publish.reconciliation_evidence = {
            **dict(publish.reconciliation_evidence or {}),
            "reconciliation": result.model_dump(mode="json"),
        }
        if comment_job:
            await transition_job(
                session, comment_job, CommentJobState.PUBLISHED, "RECONCILED_PUBLISHED"
            )
        await write_timeline(
            session,
            job=comment_job,
            event_type="comment.published",
            aggregate_id=post.id,
            payload={
                "reconciled": True,
                "external_comment_id": receipt.external_comment_id,
                "chronological_rank": chronological_rank,
                "visible_rank": visible_rank,
            },
        )
        await write_audit_log(
            session,
            action="publish.reconciled",
            resource_type="PublishJob",
            resource_id=publish.id,
            actor_type="WORKER",
            trace_id=comment_job.trace_id if comment_job else current_trace_id(),
            after={"found": True, "external_comment_id": receipt.external_comment_id},
        )
    else:
        if publish.attempt_count >= MAX_PUBLISH_ATTEMPTS:
            await finish_publish_job(session, publish, "PUBLISH_ATTEMPTS_EXHAUSTED")
            return publish
        transition(publish, CommentJobState.READY_FOR_RETRY, "RECONCILED_NOT_FOUND")
        publish.next_retry_at = utc_now() + timedelta(
            seconds=min(60, max(1, 2**publish.attempt_count))
        )
        if comment_job:
            await transition_job(
                session, comment_job, CommentJobState.READY_FOR_RETRY, "RECONCILED_NOT_FOUND"
            )
    return publish
