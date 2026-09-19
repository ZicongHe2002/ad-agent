"""Read-only context shared by review and manual-publishing screens."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import model_dict
from app.models import (
    AccountIdentityProfile,
    BrandAccount,
    Campaign,
    CommentCandidate,
    CommentQualityEvaluation,
    Creator,
    OpportunityEvaluation,
    Post,
    PostContent,
    Product,
    ProductClaim,
    VoiceProfile,
)
from app.services.capability_service import effective_capabilities


async def candidate_context(session: AsyncSession, candidate: CommentCandidate) -> dict[str, Any]:
    post = await session.get(Post, candidate.post_id)
    creator = await session.get(Creator, post.creator_id) if post else None
    content = await session.get(PostContent, candidate.post_id)
    account = await session.get(BrandAccount, candidate.brand_account_id)
    identity = await session.get(AccountIdentityProfile, account.identity_profile_id) if account else None
    voice = await session.get(VoiceProfile, account.voice_profile_id) if account else None
    campaign = await session.get(Campaign, candidate.campaign_id)
    opportunity = await session.scalar(select(OpportunityEvaluation).where(
        OpportunityEvaluation.post_id == candidate.post_id,
        OpportunityEvaluation.campaign_id == candidate.campaign_id,
    ))
    alternatives = list((await session.scalars(select(CommentCandidate).where(
        CommentCandidate.comment_job_id == candidate.comment_job_id,
        CommentCandidate.campaign_id == candidate.campaign_id,
        CommentCandidate.post_id == candidate.post_id,
    ).order_by(CommentCandidate.created_at, CommentCandidate.id))).all())
    evaluations = (await session.scalars(select(CommentQualityEvaluation).where(
        CommentQualityEvaluation.candidate_id.in_([item.id for item in alternatives]),
    ))).all()
    quality = {item.candidate_id: model_dict(item) for item in evaluations}
    claims = []
    if campaign:
        claims = list((await session.scalars(select(ProductClaim).join(Product).where(
            Product.brand_id == campaign.brand_id,
        ))).all())
    capabilities: dict[str, Any] = {}
    if post:
        effective, _ = await effective_capabilities(session, post.platform)
        capabilities = effective.model_dump(mode="json")
    return {
        "post": {**model_dict(post), "content": model_dict(content) if content else None} if post else None,
        "creator": model_dict(creator) if creator else None,
        "account": model_dict(account) if account else None,
        "identity": model_dict(identity) if identity else None,
        "voice": model_dict(voice) if voice else None,
        "campaign": model_dict(campaign) if campaign else None,
        "opportunity": model_dict(opportunity) if opportunity else None,
        "candidates": [{**model_dict(item), "quality": quality.get(item.id)} for item in alternatives],
        "claims": [model_dict(item) for item in claims],
        "capabilities": capabilities,
    }
