from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import AnchorExtractor, CommentAgent, OpportunityAgent, QualityEvaluator, RiskAgent
from app.agents.comment_agent import CommentGenerationError
from app.agents.factory import build_llm_provider
from app.api.utils import model_dict
from app.core.clock import utc_now
from app.domain.enums import (
    AnchorType,
    AuthStatus,
    BrandStatus,
    CampaignStatus,
    CandidateStatus,
    CapabilityName,
    ClaimStatus,
    CommentJobState,
    ContentProvenance,
    DisclosureStatus,
    QualityDecision,
    ReviewStatus,
    RiskDecision,
    RunMode,
)
from app.models import (
    AccountIdentityProfile,
    Brand,
    BrandAccount,
    Campaign,
    CommentCandidate,
    CommentJob,
    CommentQualityEvaluation,
    Creator,
    OpportunityEvaluation,
    Post,
    PostAnchor,
    PostContent,
    Product,
    ProductClaim,
    PublishedComment,
    ReviewJob,
    RiskEvent,
    VoiceProfile,
)
from app.observability.metrics import record_quality_decision, record_risk_decision
from app.services.capability_service import authorize_capability
from app.services.comment_service import merge_recent_comments, normalize_comment
from app.services.orchestration import (
    _disclosure_is_publishable,
    automatic_disclosure_prefix,
    ensure_publish_job,
    transition_job,
    write_timeline,
)
from app.services.publishing_policy_service import load_publishing_policy


def _plain(instance: Any) -> dict[str, Any]:
    return model_dict(instance) if instance is not None else {}


async def eligible_campaign_accounts(
    session: AsyncSession,
    post: Post,
    creator: Creator,
) -> list[tuple[Campaign, BrandAccount]]:
    stmt = (
        select(Campaign, BrandAccount)
        .join(Brand, Brand.id == Campaign.brand_id)
        .join(BrandAccount, BrandAccount.brand_id == Campaign.brand_id)
        .where(
            Campaign.status == CampaignStatus.ACTIVE,
            Brand.status == BrandStatus.ACTIVE,
            Brand.tenant_id == creator.tenant_id,
            BrandAccount.platform == post.platform,
            BrandAccount.publisher_kill_switch.is_(False),
            Campaign.publisher_kill_switch.is_(False),
            or_(Campaign.start_at.is_(None), Campaign.start_at <= utc_now()),
            or_(Campaign.end_at.is_(None), Campaign.end_at > utc_now()),
        )
        .order_by(Campaign.created_at, BrandAccount.created_at)
    )
    pairs = list((await session.execute(stmt)).all())
    chosen: list[tuple[Campaign, BrandAccount]] = []
    seen_campaigns: set[UUID] = set()
    relationship = creator.relationship_type.value
    for campaign, account in pairs:
        if campaign.id in seen_campaigns:
            continue
        if (
            campaign.creator_relationship_allowlist
            and relationship not in campaign.creator_relationship_allowlist
        ):
            continue
        seen_campaigns.add(campaign.id)
        chosen.append((campaign, account))
    return chosen


async def recent_comment_history(
    session: AsyncSession,
    *,
    account_id: UUID,
    campaign_id: UUID,
    creator_id: UUID,
) -> list[str]:
    """Load bounded history for every duplicate-control scope in the spec."""

    account_candidates = (
        await session.scalars(
            select(CommentCandidate.text)
            .where(CommentCandidate.brand_account_id == account_id)
            .order_by(CommentCandidate.created_at.desc())
            .limit(100)
        )
    ).all()
    campaign_candidates = (
        await session.scalars(
            select(CommentCandidate.text)
            .where(CommentCandidate.campaign_id == campaign_id)
            .order_by(CommentCandidate.created_at.desc())
            .limit(100)
        )
    ).all()
    creator_candidates = (
        await session.scalars(
            select(CommentCandidate.text)
            .join(Post, Post.id == CommentCandidate.post_id)
            .where(Post.creator_id == creator_id)
            .order_by(CommentCandidate.created_at.desc())
            .limit(20)
        )
    ).all()
    published = (
        await session.scalars(
            select(PublishedComment.final_text)
            .where(
                or_(
                    PublishedComment.brand_account_id == account_id,
                    PublishedComment.campaign_id == campaign_id,
                    PublishedComment.creator_id == creator_id,
                )
            )
            .order_by(PublishedComment.published_at.desc())
            .limit(100)
        )
    ).all()
    return merge_recent_comments(
        published,
        account_candidates,
        campaign_candidates,
        creator_candidates,
    )


async def analyze_post(
    session: AsyncSession,
    post_id: UUID,
    mode: RunMode | str | None = None,
) -> list[CommentJob]:
    post = await session.get(Post, post_id)
    if post is None:
        raise LookupError(f"Post {post_id} was not found")
    creator = await session.get(Creator, post.creator_id)
    content = await session.get(PostContent, post.id)
    if creator is None or content is None:
        raise RuntimeError("Post has no creator or normalized content")
    pairs = await eligible_campaign_accounts(session, post, creator)
    jobs: list[CommentJob] = []
    for campaign, account in pairs:
        run_mode = RunMode(mode) if mode else campaign.run_mode
        existing = await session.scalar(
            select(CommentJob).where(
                CommentJob.post_id == post.id,
                CommentJob.campaign_id == campaign.id,
                CommentJob.brand_account_id == account.id,
                CommentJob.intent_key == "TOP_LEVEL_PRIMARY",
            )
        )
        if existing:
            jobs.append(existing)
            continue
        job = CommentJob(
            tenant_id=creator.tenant_id,
            post_id=post.id,
            campaign_id=campaign.id,
            brand_account_id=account.id,
            run_mode=run_mode,
            intent_key="TOP_LEVEL_PRIMARY",
            trace_id=uuid4(),
            started_at=utc_now(),
        )
        session.add(job)
        await session.flush()
        await run_comment_pipeline(session, job, post, content, creator, campaign, account)
        jobs.append(job)
    if not pairs:
        await write_timeline(
            session,
            job=None,
            event_type="post.skipped",
            aggregate_id=post.id,
            payload={"reason": "NO_ELIGIBLE_ACTIVE_CAMPAIGN_ACCOUNT"},
        )
    return jobs


async def run_comment_pipeline(
    session: AsyncSession,
    job: CommentJob,
    post: Post,
    content: PostContent,
    creator: Creator,
    campaign: Campaign,
    account: BrandAccount,
) -> None:
    publishing_policy = await load_publishing_policy(session, job.tenant_id)
    provider = build_llm_provider(job.run_mode)
    await transition_job(session, job, CommentJobState.FETCHING, "NORMALIZED_CONTENT_AVAILABLE")
    await transition_job(session, job, CommentJobState.ANALYZING, "CONTENT_FETCHED")
    content_context = {**_plain(content), "external_post_id": post.external_post_id}

    extracted = await AnchorExtractor(provider=provider).extract(content_context)
    anchors: list[PostAnchor] = []
    for item in extracted.anchors:
        existing = await session.scalar(
            select(PostAnchor).where(
                PostAnchor.post_id == post.id,
                PostAnchor.anchor_type == AnchorType(item.anchor_type.value),
                PostAnchor.anchor_text == item.anchor_text,
            )
        )
        if existing:
            anchors.append(existing)
            continue
        anchor = PostAnchor(
            post_id=post.id,
            anchor_type=AnchorType(item.anchor_type.value),
            anchor_text=item.anchor_text,
            source_field=item.source_field,
            confidence=item.confidence,
        )
        session.add(anchor)
        anchors.append(anchor)
    await session.flush()
    if extracted.low_confidence or not anchors:
        await transition_job(session, job, CommentJobState.SKIPPED, "NO_CONFIDENT_CONCRETE_ANCHOR")
        return

    opportunity = await OpportunityAgent(provider=provider).evaluate(
        post=content_context,
        creator=_plain(creator),
        campaign={**_plain(campaign), "active": campaign.status == CampaignStatus.ACTIVE},
        anchors=[_plain(item) for item in anchors],
        relationship=creator.relationship_type,
    )
    evaluation = await session.scalar(
        select(OpportunityEvaluation).where(
            OpportunityEvaluation.post_id == post.id,
            OpportunityEvaluation.campaign_id == campaign.id,
        )
    )
    values = {
        key: getattr(opportunity, key)
        for key in (
            "creator_value",
            "relevance",
            "audience_match",
            "traffic_potential",
            "post_velocity",
            "brand_fit",
            "commercial_risk",
            "platform_risk",
            "final_score",
            "reason_codes",
            "prompt_version",
        )
    }
    if evaluation is None:
        evaluation = OpportunityEvaluation(post_id=post.id, campaign_id=campaign.id, **values)
        session.add(evaluation)
    else:
        for key, value in values.items():
            setattr(evaluation, key, value)
    await session.flush()
    await write_timeline(
        session,
        job=job,
        event_type="post.analysis.completed",
        aggregate_id=post.id,
        payload={"opportunity_score": opportunity.final_score, "anchors": len(anchors)},
    )
    if opportunity.final_score < 45 or opportunity.hard_blocked:
        await transition_job(session, job, CommentJobState.SKIPPED, "OPPORTUNITY_BELOW_THRESHOLD")
        return

    await transition_job(session, job, CommentJobState.GENERATING, "OPPORTUNITY_ACCEPTED")
    brand = await session.get(Brand, campaign.brand_id)
    identity = await session.get(AccountIdentityProfile, account.identity_profile_id)
    voice = await session.get(VoiceProfile, account.voice_profile_id)
    if (
        brand is None
        or identity is None
        or voice is None
        or not identity.active
        or identity.account_kind != account.account_kind
        or not voice.active
    ):
        await transition_job(session, job, CommentJobState.BLOCKED, "IDENTITY_OR_VOICE_MISSING")
        return
    current = utc_now()
    claims = (
        await session.scalars(
            select(ProductClaim)
            .join(Product, Product.id == ProductClaim.product_id)
            .where(
                Product.brand_id == brand.id,
                Product.active.is_(True),
                ProductClaim.status == ClaimStatus.APPROVED,
                ProductClaim.active.is_(True),
                or_(ProductClaim.expires_at.is_(None), ProductClaim.expires_at > current),
            )
        )
    ).all()
    recent = await recent_comment_history(
        session,
        account_id=account.id,
        campaign_id=campaign.id,
        creator_id=creator.id,
    )
    try:
        generation = await CommentAgent(provider=provider).generate_comments(
            brand={**_plain(brand), "approved_claims": [_plain(item) for item in claims]},
            account_identity=_plain(identity),
            voice_profile=_plain(voice),
            campaign={
                **_plain(campaign),
                "active": True,
                "run_mode": job.run_mode.value,
                "generation_variant": job.regeneration_count,
                "approved_claims": [_plain(item) for item in claims],
            },
            creator=_plain(creator),
            post=content_context,
            anchors=[_plain(item) for item in anchors],
            strategy=opportunity.recommended_strategy,
            recent_comments=recent,
            count=2,
        )
    except CommentGenerationError:
        # Invalid, fabricated, or duplicate provider output is a policy outcome,
        # not a transient worker crash. Never retry it into a publishable state.
        await transition_job(
            session,
            job,
            CommentJobState.QUALITY_CHECKING,
            "COMMENT_GENERATION_OUTPUT_REJECTED",
        )
        await transition_job(
            session,
            job,
            CommentJobState.BLOCKED,
            "COMMENT_GENERATION_HARD_GATE_REJECTED",
        )
        return
    generated_candidates: list[tuple[CommentCandidate, Any]] = []
    for generated in generation.candidates:
        prefix = (
            automatic_disclosure_prefix(identity)
            if publishing_policy.mode == "AUTO" and publishing_policy.auto_disclosure_enabled
            else ""
        )
        if prefix:
            generated = generated.model_copy(update={"comment": f"{prefix}{generated.comment}"})
        candidate = CommentCandidate(
            comment_job_id=job.id,
            post_id=post.id,
            campaign_id=campaign.id,
            brand_account_id=account.id,
            strategy=generated.strategy,
            text=generated.comment,
            normalized_text=normalize_comment(generated.comment),
            content_provenance=ContentProvenance.AI_GENERATED_PENDING_REVIEW,
            disclosure_status=(
                DisclosureStatus.REQUIRED_PENDING
                if (
                    identity.requires_ai_disclosure_policy_check
                    or identity.requires_brand_disclosure
                )
                else DisclosureStatus.NOT_REQUIRED
            ),
            prompt_version=generation.prompt_version,
            prompt_hash=generation.prompt_hash,
            model_provider=generation.model_provider,
            model_name=generation.model_name,
            model_request_id=generation.model_request_id,
            relevance_score=generated.relevance_score,
            commercial_score=generated.commercial_score,
            confidence=generated.confidence,
            referenced_anchor_ids=[str(item) for item in generated.referenced_anchor_ids],
            referenced_claim_ids=[str(item) for item in generated.referenced_claim_ids],
            generation_reason=generated.generation_reason,
            uses_first_person_experience=generated.uses_first_person_experience,
            implies_consumer_identity=generated.implies_consumer_identity,
            status=CandidateStatus.GENERATED,
        )
        if prefix:
            candidate.disclosure_status = DisclosureStatus.DECLARED
            candidate.disclosure_evidence = {
                "method": "automatic_comment_text",
                "identity_profile_id": str(identity.id),
                "prefix": prefix,
                "policy_version": "visible-disclosure-v1",
            }
            candidate.disclosure_resolved_at = utc_now()
        session.add(candidate)
        generated_candidates.append((candidate, generated))
    await session.flush()

    # Stage events are emitted immediately before the work they measure.  This
    # keeps generation, quality, and risk latency buckets honest.
    await transition_job(session, job, CommentJobState.QUALITY_CHECKING, "CANDIDATES_GENERATED")
    quality_candidates: list[tuple[CommentCandidate, Any, CommentQualityEvaluation]] = []
    for candidate, generated in generated_candidates:
        quality_result = QualityEvaluator().evaluate(
            generated,
            post=content_context,
            anchors=[_plain(item) for item in anchors],
            recent_comments=recent,
            approved_claims=[_plain(item) for item in claims],
            account_identity=_plain(identity),
            voice_profile=_plain(voice),
            disclosure_prefix=automatic_disclosure_prefix(identity),
        )
        quality = CommentQualityEvaluation(
            candidate_id=candidate.id,
            **{
                key: getattr(quality_result, key)
                for key in (
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
                    "decision",
                    "reasons",
                )
            },
        )
        session.add(quality)
        quality_candidates.append((candidate, quality_result, quality))
        record_quality_decision(quality.decision.value)
    await session.flush()

    await transition_job(session, job, CommentJobState.RISK_CHECKING, "QUALITY_EVALUATED")
    metadata = account.credential_metadata or {}
    raw_scopes = metadata.get("scopes", metadata.get("granted_scopes", []))
    granted_scopes = (
        [str(item) for item in raw_scopes]
        if isinstance(raw_scopes, (list, tuple, set, frozenset))
        else []
    )
    top_level_capability = await authorize_capability(
        session,
        post.platform,
        CapabilityName.TOP_LEVEL_COMMENT,
        account_type=account.account_kind.value,
        target_content_type="VIDEO",
        has_authorization=account.auth_status == AuthStatus.VALID,
        granted_scopes=granted_scopes,
        conditions_satisfied=bool(metadata.get("capability_conditions_satisfied", False)),
    )
    ai_disclosure_capability = None
    if identity.requires_ai_disclosure_policy_check:
        ai_disclosure_capability = await authorize_capability(
            session,
            post.platform,
            CapabilityName.AI_DISCLOSURE,
            account_type=account.account_kind.value,
            target_content_type="VIDEO",
            has_authorization=account.auth_status == AuthStatus.VALID,
            granted_scopes=granted_scopes,
            conditions_satisfied=bool(metadata.get("capability_conditions_satisfied", False)),
        )

    candidates: list[tuple[CommentCandidate, CommentQualityEvaluation, RiskEvent]] = []
    normalized_brand_name = normalize_comment(brand.name)
    for candidate, quality_result, quality in quality_candidates:
        brand_mentioned = bool(
            normalized_brand_name and normalized_brand_name in normalize_comment(candidate.text)
        )
        uncertain_categories = (
            list(quality.reasons) if quality.decision == QualityDecision.REVIEW else []
        )
        if creator.relationship_type.value == "GENERAL_CREATOR" and brand_mentioned:
            uncertain_categories.append("GENERAL_CREATOR_BRAND_MENTION")
        if candidate.disclosure_status in {
            DisclosureStatus.REQUIRED_PENDING,
            DisclosureStatus.UNKNOWN,
        }:
            uncertain_categories.append("DISCLOSURE_UNRESOLVED")
        if not top_level_capability.allowed:
            uncertain_categories.append(f"TOP_LEVEL_CAPABILITY_{top_level_capability.reason}")
        if ai_disclosure_capability is not None and not ai_disclosure_capability.allowed:
            uncertain_categories.append(
                f"AI_DISCLOSURE_CAPABILITY_{ai_disclosure_capability.reason}"
            )
        if candidate.referenced_claim_ids:
            uncertain_categories.append("PRODUCT_CLAIM_PRESENT")
        risk_context = {
            "comment": candidate.text,
            "post": content_context,
            "account_identity": _plain(identity),
            "approved_claims": [_plain(item) for item in claims],
            "creator_relationship": creator.relationship_type.value,
            "brand_mentioned": brand_mentioned,
            "fake_experience": quality.fake_experience_detected,
            "fake_identity": quality.fake_identity_detected,
            "unapproved_claim": quality.unsupported_claim_detected,
            "external_contact": quality_result.external_contact_detected,
            "account_kill_switch": account.publisher_kill_switch,
            "campaign_kill_switch": campaign.publisher_kill_switch,
            "identity_missing": False,
            "disclosure_unresolved": candidate.disclosure_status
            in {DisclosureStatus.REQUIRED_PENDING, DisclosureStatus.UNKNOWN},
            "capability_manual_required": not top_level_capability.allowed,
            "capability_reason": top_level_capability.reason,
            "uncertain_categories": list(dict.fromkeys(uncertain_categories)),
        }
        risk_result = await RiskAgent(provider=provider).evaluate(risk_context)
        if quality.decision == QualityDecision.BLOCK:
            risk_result.decision = RiskDecision.BLOCK
            risk_result.risk_score = 1.0
            risk_result.reasons = list(dict.fromkeys([*risk_result.reasons, *quality.reasons]))
        risk = RiskEvent(
            candidate_id=candidate.id,
            rule_decision=RiskDecision.BLOCK
            if quality.decision == QualityDecision.BLOCK
            else RiskDecision.ALLOW,
            llm_decision=None,
            final_decision=risk_result.decision,
            risk_score=risk_result.risk_score,
            matched_rules=risk_result.matched_policy_categories,
            reasons=risk_result.reasons,
            policy_versions={"rules": "v1", "quality": "v1"},
        )
        session.add(risk)
        record_risk_decision(risk.final_decision.value)
        candidates.append((candidate, quality, risk))
    await session.flush()

    nonblocked = [
        item
        for item in candidates
        if item[1].decision != QualityDecision.BLOCK
        and item[2].final_decision != RiskDecision.BLOCK
    ]
    if not nonblocked:
        for candidate, _, _ in candidates:
            candidate.status = CandidateStatus.BLOCKED
        await transition_job(session, job, CommentJobState.BLOCKED, "ALL_CANDIDATES_BLOCKED")
        return
    selected, quality, risk = max(nonblocked, key=lambda item: float(item[1].quality_score))
    job.selected_candidate_id = selected.id
    selected.status = CandidateStatus.SELECTED
    for candidate, _, _ in candidates:
        if candidate.id != selected.id:
            candidate.status = CandidateStatus.REJECTED

    auto_allowed = (
        quality.decision == QualityDecision.ALLOW
        and risk.final_decision == RiskDecision.ALLOW
        and account.auto_publish_enabled
        and publishing_policy.mode == "AUTO"
        and not campaign.human_review_required
        and account.auth_status == AuthStatus.VALID
        and top_level_capability.allowed
        and (ai_disclosure_capability is None or ai_disclosure_capability.allowed)
        and _disclosure_is_publishable(selected, identity)
    )
    if auto_allowed:
        selected.content_provenance = ContentProvenance.AI_GENERATED_AUTO_APPROVED
        await transition_job(session, job, CommentJobState.READY, "ALL_AUTO_PUBLISH_GATES_PASSED")
        await ensure_publish_job(session, job, selected)
        return
    if publishing_policy.mode == "AUTO":
        reasons = []
        if not account.auto_publish_enabled:
            reasons.append("ACCOUNT_AUTO_PUBLISH_DISABLED")
        if campaign.human_review_required:
            reasons.append("CAMPAIGN_REQUIRES_REVIEW")
        if account.auth_status != AuthStatus.VALID:
            reasons.append("ACCOUNT_AUTHORIZATION_REQUIRED")
        if not top_level_capability.allowed:
            reasons.append(f"TOP_LEVEL_CAPABILITY_{top_level_capability.reason}")
        if ai_disclosure_capability is not None and not ai_disclosure_capability.allowed:
            reasons.append(f"AI_DISCLOSURE_CAPABILITY_{ai_disclosure_capability.reason}")
        if not _disclosure_is_publishable(selected, identity):
            reasons.append("DISCLOSURE_UNRESOLVED")
        if quality.decision != QualityDecision.ALLOW:
            reasons.extend(quality.reasons or ["QUALITY_NOT_ALLOWED"])
        if risk.final_decision != RiskDecision.ALLOW:
            reasons.extend(risk.reasons or ["RISK_NOT_ALLOWED"])
        await transition_job(session, job, CommentJobState.SKIPPED, "AUTO_PUBLISH_CHECKS_NOT_PASSED")
        await write_timeline(
            session, job=job, event_type="comment.automation.skipped", aggregate_id=post.id,
            payload={"reasons": list(dict.fromkeys(reasons))},
        )
        return
    review = ReviewJob(
        candidate_id=selected.id,
        status=ReviewStatus.PENDING,
        submitted_at=utc_now(),
        expires_at=utc_now() + timedelta(hours=24),
        original_candidate_text=selected.text,
    )
    session.add(review)
    await transition_job(session, job, CommentJobState.WAITING_REVIEW, "HUMAN_REVIEW_REQUIRED")
    await write_timeline(
        session,
        job=job,
        event_type="review.requested",
        aggregate_id=post.id,
        payload={"candidate_id": str(selected.id)},
    )


async def regenerate_comment_job(
    session: AsyncSession,
    job_id: UUID,
    reason: str,
) -> CommentJob:
    job = await session.scalar(select(CommentJob).where(CommentJob.id == job_id).with_for_update())
    if job is None:
        raise LookupError(f"CommentJob {job_id} was not found")
    if job.regeneration_count >= job.max_regenerations:
        raise ValueError("regeneration limit reached")
    if job.state != CommentJobState.WAITING_REVIEW:
        raise ValueError("only a review-pending job can be regenerated")
    reviews = (
        await session.scalars(
            select(ReviewJob)
            .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
            .where(
                CommentCandidate.comment_job_id == job.id, ReviewJob.status == ReviewStatus.PENDING
            )
        )
    ).all()
    for review in reviews:
        review.status = ReviewStatus.EXPIRED
        review.resolved_at = utc_now()
        review.review_notes = f"Regenerated: {reason}"
    next_regeneration = job.regeneration_count + 1
    await transition_job(session, job, CommentJobState.SKIPPED, "REGENERATED_SUPERSEDED")
    post = await session.get(Post, job.post_id)
    content = await session.get(PostContent, job.post_id)
    campaign = await session.get(Campaign, job.campaign_id)
    account = await session.get(BrandAccount, job.brand_account_id)
    creator = await session.get(Creator, post.creator_id) if post else None
    if post is None or content is None or campaign is None or account is None or creator is None:
        raise RuntimeError("regeneration context is incomplete")
    replacement = CommentJob(
        tenant_id=job.tenant_id,
        post_id=job.post_id,
        campaign_id=job.campaign_id,
        brand_account_id=job.brand_account_id,
        run_mode=job.run_mode,
        intent_key=f"TOP_LEVEL_REGEN_{next_regeneration}",
        trace_id=job.trace_id,
        started_at=utc_now(),
        regeneration_count=next_regeneration,
        max_regenerations=job.max_regenerations,
    )
    session.add(replacement)
    await session.flush()
    await write_timeline(
        session,
        job=replacement,
        event_type="comment.generation.started",
        aggregate_id=replacement.post_id,
        payload={
            "regeneration_count": replacement.regeneration_count,
            "reason": reason,
            "superseded_job_id": str(job.id),
        },
    )
    await run_comment_pipeline(
        session,
        replacement,
        post,
        content,
        creator,
        campaign,
        account,
    )
    return replacement
