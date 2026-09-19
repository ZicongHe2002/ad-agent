from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.clock import utc_now
from app.core.security import hash_password
from app.domain.enums import (
    AccountKind,
    AuthStatus,
    CampaignStatus,
    CapabilityStatus,
    CommentJobState,
    CreatorRelationship,
    DisclosureStatus,
    MonitorState,
    Platform,
    RunMode,
    UserRole,
    UserStatus,
)
from app.models import (
    AccountIdentityProfile,
    Brand,
    BrandAccount,
    Campaign,
    CommentCandidate,
    CommentJob,
    Creator,
    CreatorPlatformAccount,
    Post,
    PublishedComment,
    PublishJob,
    ReviewJob,
    Tenant,
    TimelineEvent,
    User,
    VoiceProfile,
)
from app.platforms.errors import PlatformTemporaryError, PublishUncertainError
from app.platforms.mock.failure_injection import MockFailureProfile
from app.platforms.runtime import mock_service
from app.services.discovery_service import poll_creator_accounts
from app.services.maintenance_service import run_maintenance_once
from app.services.orchestration import resolve_review
from app.services.pipeline_service import analyze_post
from app.services.publisher_runtime import publish_comment_job, reconcile_publish_job

TEST_DISCLOSURE = {
    "disclosure_status": DisclosureStatus.DECLARED,
    "disclosure_evidence": {
        "source": "mock-policy-v1",
        "note": "Mock official account identity and AI disclosure control explicitly confirmed",
    },
}


async def _seed(factory) -> dict:
    await mock_service.reset()
    external_creator_id = f"creator-{uuid4()}"
    await mock_service.create_creator("羊绒搭配作者", external_creator_id=external_creator_id)
    async with factory() as session, session.begin():
        tenant = Tenant(name="Test", slug=f"test-{uuid4().hex[:8]}")
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            email=f"admin-{uuid4().hex[:8]}@example.com",
            display_name="Admin",
            password_hash=hash_password("test-password"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        brand = Brand(
            tenant_id=tenant.id,
            name="云绒",
            description="羊绒 秋冬 穿搭",
        )
        session.add_all([user, brand])
        await session.flush()
        identity = AccountIdentityProfile(
            tenant_id=tenant.id,
            legal_or_operating_entity="云绒品牌公司",
            account_kind=AccountKind.BRAND_OFFICIAL,
            public_identity_text="云绒官方账号",
            requires_brand_disclosure=True,
            requires_ai_disclosure_policy_check=True,
        )
        voice = VoiceProfile(
            brand_id=brand.id,
            name="官方友好",
            tone_attributes=["具体", "克制"],
            forbidden_phrases=["我买过", "亲测", "回购"],
        )
        session.add_all([identity, voice])
        await session.flush()
        account = BrandAccount(
            brand_id=brand.id,
            platform=Platform.MOCK,
            external_account_id=f"brand-{uuid4()}",
            display_name="云绒官方",
            account_kind=AccountKind.BRAND_OFFICIAL,
            identity_profile_id=identity.id,
            voice_profile_id=voice.id,
            auto_publish_enabled=False,
            auth_status=AuthStatus.VALID,
        )
        campaign = Campaign(
            brand_id=brand.id,
            name="羊绒 秋冬 穿搭",
            run_mode=RunMode.FAST,
            status=CampaignStatus.ACTIVE,
            creator_relationship_allowlist=[CreatorRelationship.PARTNER_CREATOR.value],
            max_comments_per_day=20,
            max_comments_per_creator_per_day=3,
            human_review_required=True,
        )
        creator = Creator(
            tenant_id=tenant.id,
            name="羊绒搭配作者",
            category="时尚",
            relationship_type=CreatorRelationship.PARTNER_CREATOR,
            priority=100,
            monitor_state=MonitorState.ACTIVE,
        )
        session.add_all([account, campaign, creator])
        await session.flush()
        session.add(
            CreatorPlatformAccount(
                creator_id=creator.id,
                platform=Platform.MOCK,
                external_creator_id=external_creator_id,
            )
        )
        return {
            "user_id": user.id,
            "creator_id": creator.id,
            "account_id": account.id,
            "external_creator_id": external_creator_id,
        }


async def _create_review_case(factory, *, existing_comments: int = 0) -> dict:
    context = await _seed(factory)
    external_post_id = f"post-{uuid4()}"
    await mock_service.create_post(
        context["external_creator_id"],
        external_post_id=external_post_id,
        title="奶油白羊绒大衣",
        caption="深棕围巾配直筒裤，秋冬层次很清楚",
        hashtags=["羊绒", "秋冬穿搭"],
    )
    if existing_comments:
        await mock_service.simulate_comments(external_post_id, existing_comments)
    async with factory() as session:
        result = await poll_creator_accounts(session, context["creator_id"])
        assert result["inserted"] == 1
        await session.commit()
        post = await session.scalar(select(Post).where(Post.external_post_id == external_post_id))
        jobs = await analyze_post(session, post.id)
        await session.commit()
        assert len(jobs) == 1
        assert jobs[0].state == CommentJobState.WAITING_REVIEW
        review = await session.scalar(
            select(ReviewJob)
            .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
            .where(CommentCandidate.post_id == post.id)
        )
        candidate = await session.get(CommentCandidate, review.candidate_id)
        context.update(
            {
                "post_id": post.id,
                "external_post_id": external_post_id,
                "job_id": jobs[0].id,
                "review_id": review.id,
                "candidate_id": candidate.id,
                "candidate_text": candidate.text,
                "anchor_id": candidate.referenced_anchor_ids[0],
            }
        )
    return context


async def _approve_and_publish(factory, context: dict) -> PublishedComment:
    async with factory() as session:
        await resolve_review(
            session,
            context["review_id"],
            context["user_id"],
            action="approve",
            notes="e2e approval",
            **TEST_DISCLOSURE,
        )
        await session.commit()
        publish = await session.scalar(
            select(PublishJob).where(PublishJob.comment_job_id == context["job_id"])
        )
        published = await publish_comment_job(session, publish.id)
        await session.commit()
        return published


@pytest.mark.parametrize("existing_comments,expected_rank", [(0, 1), (3, 4), (5, 6)])
async def test_first_top5_and_not_top5(
    clean_database, existing_comments: int, expected_rank: int
) -> None:
    context = await _create_review_case(clean_database, existing_comments=existing_comments)
    published = await _approve_and_publish(clean_database, context)
    assert published.chronological_rank == expected_rank
    assert (published.chronological_rank <= 5) is (expected_rank <= 5)


async def test_fake_consumer_edit_is_blocked(clean_database) -> None:
    context = await _create_review_case(clean_database)
    anchor = context["candidate_text"].split("这个细节", 1)[0]
    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await resolve_review(
                session,
                context["review_id"],
                context["user_id"],
                action="edit-and-approve",
                final_text=f"{anchor}我买过，亲测很好。",
                notes="unsafe edit",
                **TEST_DISCLOSURE,
            )
        assert error.value.status_code == 422
        assert await session.scalar(select(func.count()).select_from(PublishJob)) == 0


async def test_generic_comment_without_anchor_is_blocked(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        with pytest.raises(HTTPException) as error:
            await resolve_review(
                session,
                context["review_id"],
                context["user_id"],
                action="edit-and-approve",
                final_text="好好看，支持一下",
                notes="generic edit",
                **TEST_DISCLOSURE,
            )
        assert error.value.status_code == 422


async def test_duplicate_candidate_is_blocked_before_publish(clean_database) -> None:
    context = await _create_review_case(clean_database)
    await _approve_and_publish(clean_database, context)
    duplicate_post_id = f"duplicate-post-{uuid4()}"
    await mock_service.create_post(
        context["external_creator_id"],
        external_post_id=duplicate_post_id,
        title="奶油白羊绒大衣",
        caption="深棕围巾配直筒裤，秋冬层次很清楚",
        hashtags=["羊绒", "秋冬穿搭"],
    )
    async with clean_database() as session:
        result = await poll_creator_accounts(session, context["creator_id"])
        assert result["inserted"] == 1
        duplicate_post = await session.scalar(
            select(Post).where(Post.external_post_id == duplicate_post_id)
        )
        jobs = await analyze_post(session, duplicate_post.id)
        await session.commit()
        assert jobs[0].state == CommentJobState.BLOCKED
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PublishJob)
                .where(PublishJob.comment_job_id == jobs[0].id)
            )
            == 0
        )


async def test_unknown_publish_capability_routes_to_manual(clean_database) -> None:
    await mock_service.configure_capabilities(top_level_comment=CapabilityStatus.UNKNOWN)
    context = await _create_review_case(clean_database)
    # _seed resets Mock state; set UNKNOWN after discovery so current routing is safe.
    await mock_service.configure_capabilities(top_level_comment=CapabilityStatus.UNKNOWN)
    async with clean_database() as session:
        result = await resolve_review(
            session,
            context["review_id"],
            context["user_id"],
            action="approve",
            **TEST_DISCLOSURE,
        )
        await session.commit()
        assert result["publish_job"]["state"] == "WAITING_MANUAL_PUBLISH"
        assert result["publish_job"]["mode"] == "MANUAL"
        assert (
            len(
                (
                    await mock_service.get_comments(
                        context["external_post_id"], inject_failure=False
                    )
                ).items
            )
            == 0
        )


async def test_success_but_timeout_reconciles_once(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        await session.commit()
        publish = await session.scalar(select(PublishJob))
        await mock_service.configure_failure_profile(
            MockFailureProfile(publish_success_but_timeout_rate=1.0)
        )
        with pytest.raises(PublishUncertainError):
            await publish_comment_job(session, publish.id)
        await session.commit()
        assert publish.state == CommentJobState.PUBLISH_UNCERTAIN
        publish.next_retry_at = utc_now() - timedelta(seconds=1)
        await reconcile_publish_job(session, publish.id)
        await session.commit()
        assert publish.state == CommentJobState.PUBLISHED
    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert len(comments.items) == 1


async def test_retryable_platform_failure_is_durable_before_reconcile(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        await session.commit()
        publish = await session.scalar(select(PublishJob))
        await mock_service.configure_failure_profile(MockFailureProfile(http_500_rate=1.0))
        with pytest.raises(PlatformTemporaryError):
            await publish_comment_job(session, publish.id)
        await session.commit()
        assert publish.state == CommentJobState.PUBLISH_UNCERTAIN
        assert publish.last_error_code == "platform_temporary_error"
        assert publish.next_retry_at is not None

        await mock_service.configure_failure_profile(MockFailureProfile())
        publish.next_retry_at = utc_now() - timedelta(seconds=1)
        await reconcile_publish_job(session, publish.id)
        await session.commit()
        assert publish.state == CommentJobState.READY_FOR_RETRY

    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert comments.items == []


async def test_disclosure_pending_never_auto_publishes(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        candidate = await session.get(CommentCandidate, context["candidate_id"])
        assert candidate.disclosure_status == DisclosureStatus.REQUIRED_PENDING
        assert await session.scalar(select(func.count()).select_from(PublishJob)) == 0


async def test_account_kill_switch_blocks_before_external_call(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        account = await session.get(BrandAccount, context["account_id"])
        account.publisher_kill_switch = True
        await session.commit()
        publish = await session.scalar(select(PublishJob))
        with pytest.raises(PermissionError, match="Kill switch"):
            await publish_comment_job(session, publish.id)
    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert comments.items == []


async def test_campaign_kill_switch_blocks_before_external_call(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        candidate = await session.get(CommentCandidate, context["candidate_id"])
        campaign = await session.get(Campaign, candidate.campaign_id)
        campaign.publisher_kill_switch = True
        await session.commit()
        publish = await session.scalar(select(PublishJob))
        with pytest.raises(PermissionError, match="Kill switch"):
            await publish_comment_job(session, publish.id)
    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert comments.items == []


async def test_platform_kill_switch_blocks_before_external_call(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        await session.commit()
        await mock_service.configure_capabilities(top_level_comment=CapabilityStatus.DISABLED)
        publish = await session.scalar(select(PublishJob))
        with pytest.raises(PermissionError, match="capability registry"):
            await publish_comment_job(session, publish.id)
    comments = await mock_service.get_comments(context["external_post_id"], inject_failure=False)
    assert comments.items == []


async def test_expired_review_is_closed_by_maintenance(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        review = await session.get(ReviewJob, context["review_id"])
        review.expires_at = utc_now() - timedelta(minutes=1)
        await session.commit()

        result = await run_maintenance_once(session)
        await session.commit()
        job = await session.get(CommentJob, context["job_id"])
        assert result.expired_review_ids == [review.id]
        assert review.status.value == "EXPIRED"
        assert job.state == CommentJobState.SKIPPED


async def test_stuck_publish_is_reconciled_instead_of_blindly_retried(clean_database) -> None:
    context = await _create_review_case(clean_database)
    async with clean_database() as session:
        await resolve_review(session, context["review_id"], context["user_id"], action="approve", **TEST_DISCLOSURE)
        publish = await session.scalar(select(PublishJob))
        job = await session.get(CommentJob, context["job_id"])
        from app.domain.state_machine import transition
        from app.services.orchestration import transition_job

        transition(publish, CommentJobState.PUBLISHING, "TEST_WORKER_STARTED")
        await transition_job(session, job, CommentJobState.PUBLISHING, "TEST_WORKER_STARTED")
        publish.started_at = utc_now() - timedelta(minutes=5)
        await session.commit()

        result = await run_maintenance_once(session)
        await session.commit()
        assert result.reconcile_publish_ids == [publish.id]
        assert publish.state == CommentJobState.PUBLISH_UNCERTAIN
        assert job.state == CommentJobState.PUBLISH_UNCERTAIN


async def test_full_timeline_and_audit_path(clean_database) -> None:
    context = await _create_review_case(clean_database, existing_comments=3)
    published = await _approve_and_publish(clean_database, context)
    async with clean_database() as session:
        events = (
            await session.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.aggregate_id == context["post_id"])
                .order_by(TimelineEvent.occurred_at)
            )
        ).all()
        names = {item.event_type for item in events}
        assert {
            "post.detected",
            "post.analysis.completed",
            "review.requested",
            "comment.published",
        } <= names
        assert published.chronological_rank == 4
