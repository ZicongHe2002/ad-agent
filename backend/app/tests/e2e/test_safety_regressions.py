from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agents.quality_evaluator import QualityEvaluator
from app.agents.risk_agent import RiskAgent
from app.core.clock import utc_now
from app.domain.enums import (
    CapabilityName,
    CapabilityStatus,
    ClaimStatus,
    CommentJobState,
    DisclosureStatus,
    Platform,
    PublishMode,
)
from app.models import (
    Brand,
    BrandAccount,
    Campaign,
    CapabilityRecord,
    CommentCandidate,
    Product,
    ProductClaim,
    PublishJob,
    ReviewJob,
    TimelineEvent,
)
from app.platforms.runtime import mock_service
from app.services.comment_service import normalize_comment
from app.services.orchestration import resolve_review, select_review_candidate
from app.services.pipeline_service import regenerate_comment_job
from app.services.publisher_runtime import publish_comment_job
from app.tests.e2e.test_workflow import _create_review_case

DISCLOSURE_EVIDENCE = {
    "source": "reviewer",
    "method": "explicit disclosure confirmation",
}


async def _approve_with_disclosure(session, context: dict) -> dict:
    return await resolve_review(
        session,
        context["review_id"],
        context["user_id"],
        action="approve",
        disclosure_status=DisclosureStatus.DECLARED,
        disclosure_evidence=DISCLOSURE_EVIDENCE,
    )


async def _add_claim(factory, context: dict, *, text: str, expired: bool = False) -> ProductClaim:
    async with factory() as session:
        brand = await session.scalar(select(Brand))
        assert brand is not None
        product = Product(
            brand_id=brand.id,
            name=f"Safety product {uuid4()}",
            category="test",
        )
        session.add(product)
        await session.flush()
        approved_at = utc_now() - timedelta(days=2) if expired else utc_now()
        claim = ProductClaim(
            product_id=product.id,
            claim_text=text,
            evidence={"source": "safety regression"},
            status=ClaimStatus.APPROVED,
            approved_by_user_id=context["user_id"],
            approved_at=approved_at,
            expires_at=(utc_now() - timedelta(days=1))
            if expired
            else (utc_now() + timedelta(days=1)),
            active=True,
        )
        session.add(claim)
        await session.commit()
        return claim


async def test_mixed_approved_and_unapproved_claim_is_blocked(clean_database) -> None:
    context = await _create_review_case(clean_database)
    await _add_claim(clean_database, context, text="羊绒")

    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await resolve_review(
                session,
                context["review_id"],
                context["user_id"],
                action="edit-and-approve",
                final_text="秋冬穿搭很清楚，我们的羊绒大衣保证永久治愈皮肤病。",
                notes="must remain blocked",
                disclosure_status=DisclosureStatus.DECLARED,
                disclosure_evidence=DISCLOSURE_EVIDENCE,
            )
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "EDIT_FAILED_QUALITY_GATES"
        assert "UNSUPPORTED_CLAIM" in error.value.detail["reasons"]
        assert await session.scalar(select(PublishJob)) is None


async def test_review_approval_cannot_erase_pending_disclosure(clean_database) -> None:
    context = await _create_review_case(clean_database)

    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await resolve_review(
                session,
                context["review_id"],
                context["user_id"],
                action="approve",
            )
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "DISCLOSURE_RESOLUTION_REQUIRED"
        candidate = await session.get(CommentCandidate, context["candidate_id"])
        assert candidate is not None
        assert candidate.disclosure_status == DisclosureStatus.REQUIRED_PENDING
        assert candidate.disclosure_evidence == {}
        assert await session.scalar(select(PublishJob)) is None


async def test_explicit_disclosure_resolution_is_persisted(clean_database) -> None:
    context = await _create_review_case(clean_database)

    async with clean_database() as session:
        result = await _approve_with_disclosure(session, context)
        candidate = await session.get(CommentCandidate, context["candidate_id"])
        assert candidate is not None
        assert candidate.disclosure_status == DisclosureStatus.DECLARED
        assert candidate.disclosure_evidence == DISCLOSURE_EVIDENCE
        assert candidate.disclosure_resolved_by_user_id == context["user_id"]
        assert candidate.disclosure_resolved_at is not None
        assert result["publish_job"]["state"] == CommentJobState.READY.value


async def test_expired_review_is_rejected_in_resolution_transaction(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        review = await session.get(ReviewJob, context["review_id"])
        assert review is not None
        review.expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await _approve_with_disclosure(session, context)
        assert error.value.status_code == 410
        assert error.value.detail["code"] == "REVIEW_JOB_EXPIRED"
        assert await session.scalar(select(PublishJob)) is None


async def test_expired_claim_cannot_be_laundered_by_review(clean_database) -> None:
    context = await _create_review_case(clean_database)
    claim = await _add_claim(clean_database, context, text="羊绒", expired=True)
    async with clean_database() as session:
        candidate = await session.get(CommentCandidate, context["candidate_id"])
        assert candidate is not None
        candidate.text = "秋冬穿搭与羊绒这一信息很契合。"
        candidate.normalized_text = normalize_comment(candidate.text)
        candidate.referenced_claim_ids = [str(claim.id)]
        await session.commit()

    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await _approve_with_disclosure(session, context)
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "REFERENCED_CLAIM_NO_LONGER_APPROVED"
        assert await session.scalar(select(PublishJob)) is None


async def test_out_of_scope_supported_capability_routes_to_manual(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        session.add(
            CapabilityRecord(
                platform=Platform.MOCK,
                capability=CapabilityName.TOP_LEVEL_COMMENT,
                status=CapabilityStatus.SUPPORTED,
                source_title="Scoped safety fixture",
                source_owner="tests",
                verified_at=utc_now(),
                expires_at=utc_now() + timedelta(days=1),
                scope={
                    "account_types": ["HUMAN_OPERATOR"],
                    "target_content_types": ["VIDEO"],
                    "authorization_required": True,
                },
            )
        )
        await session.commit()

    async with clean_database() as session:
        result = await _approve_with_disclosure(session, context)
        publish = result["publish_job"]
        assert publish["state"] == CommentJobState.WAITING_MANUAL_PUBLISH.value
        assert publish["mode"] == PublishMode.MANUAL.value
        decision = publish["reconciliation_evidence"]["capability_decision"]
        assert decision["top_level_comment"]["reason"] == "ACCOUNT_TYPE_OUT_OF_SCOPE"


async def test_mock_regeneration_produces_new_reviewable_candidates(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        old_texts = set(
            (
                await session.scalars(
                    select(CommentCandidate.text).where(
                        CommentCandidate.comment_job_id == context["job_id"]
                    )
                )
            ).all()
        )
        replacement = await regenerate_comment_job(
            session,
            context["job_id"],
            "request a distinct compliant alternative",
        )
        new_texts = set(
            (
                await session.scalars(
                    select(CommentCandidate.text).where(
                        CommentCandidate.comment_job_id == replacement.id
                    )
                )
            ).all()
        )
        assert replacement.state == CommentJobState.WAITING_REVIEW
        assert len(new_texts) == 2
        assert old_texts.isdisjoint(new_texts)
        assert await session.scalar(
            select(ReviewJob)
            .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
            .where(CommentCandidate.comment_job_id == replacement.id)
        )


async def test_quality_and_risk_stage_events_wrap_actual_work(clean_database, monkeypatch) -> None:
    original_quality = QualityEvaluator.evaluate
    original_risk = RiskAgent.evaluate

    def delayed_quality(self, *args, **kwargs):
        time.sleep(0.02)
        return original_quality(self, *args, **kwargs)

    async def delayed_risk(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        return await original_risk(self, *args, **kwargs)

    monkeypatch.setattr(QualityEvaluator, "evaluate", delayed_quality)
    monkeypatch.setattr(RiskAgent, "evaluate", delayed_risk)
    context = await _create_review_case(clean_database)

    async with clean_database() as session:
        events = (
            await session.scalars(
                select(TimelineEvent)
                .where(
                    TimelineEvent.comment_job_id == context["job_id"],
                    TimelineEvent.event_type.in_(
                        [
                            "job.quality_checking",
                            "job.risk_checking",
                            "job.waiting_review",
                        ]
                    ),
                )
                .order_by(TimelineEvent.occurred_at)
            )
        ).all()
        by_name = {item.event_type: item.occurred_at for item in events}
        assert (
            by_name["job.risk_checking"] - by_name["job.quality_checking"]
        ).total_seconds() >= 0.03
        assert (
            by_name["job.waiting_review"] - by_name["job.risk_checking"]
        ).total_seconds() >= 0.03


async def test_inflight_publish_reservation_consumes_last_account_slot(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await _approve_with_disclosure(session, context)
        account = await session.get(BrandAccount, context["account_id"])
        assert account is not None
        account.max_comments_per_day = 1
        campaign = await session.scalar(select(Campaign))
        assert campaign is not None
        campaign.max_comments_per_day = 10
        alternatives = (
            await session.scalars(
                select(CommentCandidate).where(
                    CommentCandidate.comment_job_id == context["job_id"],
                    CommentCandidate.id != context["candidate_id"],
                )
            )
        ).all()
        assert alternatives
        current_publish = await session.scalar(
            select(PublishJob).where(PublishJob.candidate_id == context["candidate_id"])
        )
        assert current_publish is not None
        session.add(
            PublishJob(
                candidate_id=alternatives[0].id,
                brand_account_id=account.id,
                capability_snapshot_id=current_publish.capability_snapshot_id,
                platform=Platform.MOCK,
                mode=PublishMode.OFFICIAL_API,
                idempotency_key=f"safety-reservation-{uuid4()}",
                state=CommentJobState.PUBLISHING,
                state_reason="SAFETY_TEST_RESERVATION",
                started_at=utc_now(),
            )
        )
        await session.commit()

    async with clean_database() as session:
        publish = await session.scalar(
            select(PublishJob).where(PublishJob.candidate_id == context["candidate_id"])
        )
        assert publish is not None
        with pytest.raises(PermissionError, match="Account daily limit exceeded"):
            await publish_comment_job(session, publish.id)
    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert comments.items == []


async def test_review_candidate_selection_requires_claim_and_rechecks_eligibility(
    clean_database,
) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        review = await session.get(ReviewJob, context["review_id"])
        assert review is not None
        review.assigned_to = context["user_id"]
        alternative = await session.scalar(
            select(CommentCandidate).where(
                CommentCandidate.comment_job_id == context["job_id"],
                CommentCandidate.id != context["candidate_id"],
            )
        )
        assert alternative is not None
        await session.commit()

    async with clean_database() as session:
        result = await select_review_candidate(
            session,
            context["review_id"],
            alternative.id,
            context["user_id"],
        )
        assert result["candidate"]["id"] == str(alternative.id)
        assert result["candidate"]["status"] == "SELECTED"
