from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.enums import CapabilityStatus, CommentJobState, DisclosureStatus, UserRole
from app.main import app
from app.models import BrandAccount, Campaign, Post, PublishingSettings, PublishJob, ReviewJob, User
from app.platforms.runtime import mock_service
from app.services.discovery_service import poll_creator_accounts
from app.services.pipeline_service import analyze_post
from app.services.publisher_runtime import publish_comment_job
from app.services.publishing_policy_service import publishing_scope_key
from app.tests.e2e.test_workflow import _seed


async def setup_case(factory, mode="AUTO", disclosure=True):
    context = await _seed(factory)
    async with factory() as session:
        user = await session.get(User, context["user_id"])
        session.add(PublishingSettings(
            scope_key=publishing_scope_key(user.tenant_id), tenant_id=user.tenant_id,
            mode=mode, auto_disclosure_enabled=disclosure,
        ))
        account = await session.get(BrandAccount, context["account_id"])
        account.auto_publish_enabled = True
        campaign = await session.scalar(select(Campaign))
        campaign.human_review_required = False
        context["tenant_id"] = user.tenant_id
        await session.commit()
    await mock_service.create_post(
        context["external_creator_id"], external_post_id="auto-mode-post",
        title="奶油白羊绒大衣", caption="深棕围巾配直筒裤，秋冬层次很清楚",
        hashtags=["羊绒", "秋冬穿搭"],
    )
    async with factory() as session:
        await poll_creator_accounts(session, context["creator_id"])
        post = await session.scalar(select(Post))
        context["post_id"] = post.id
        await session.commit()
    return context


async def test_review_mode_always_requires_review_even_with_account_opt_in(clean_database):
    context = await setup_case(clean_database, mode="REVIEW")
    async with clean_database() as session:
        jobs = await analyze_post(session, context["post_id"])
        assert jobs[0].state == CommentJobState.WAITING_REVIEW
        assert await session.scalar(select(func.count()).select_from(ReviewJob)) == 1
        assert await session.scalar(select(PublishJob)) is None


async def test_auto_mode_publishes_visible_disclosure_without_individual_approval(clean_database):
    context = await setup_case(clean_database)
    async with clean_database() as session:
        jobs = await analyze_post(session, context["post_id"])
        assert jobs[0].state == CommentJobState.READY
        assert await session.scalar(select(func.count()).select_from(ReviewJob)) == 0
        await session.commit()
        publish = await session.scalar(select(PublishJob))
        published = await publish_comment_job(session, publish.id)
        await session.commit()
        assert published.final_text.startswith("【云绒官方账号｜AI辅助生成】")
        assert published.disclosure_status == DisclosureStatus.DECLARED
    comments = await mock_service.get_comments("auto-mode-post", inject_failure=False)
    assert len(comments.items) == 1
    assert comments.items[0].text == published.final_text


@pytest.mark.parametrize("missing", ["disclosure", "capability"])
async def test_auto_mode_skips_unresolved_checks_without_sending_or_review_queue(clean_database, missing):
    context = await setup_case(clean_database, disclosure=missing != "disclosure")
    if missing == "capability":
        await mock_service.configure_capabilities(top_level_comment=CapabilityStatus.UNKNOWN)
    async with clean_database() as session:
        jobs = await analyze_post(session, context["post_id"])
        assert jobs[0].state == CommentJobState.SKIPPED
        assert jobs[0].state_reason == "AUTO_PUBLISH_CHECKS_NOT_PASSED"
        assert await session.scalar(select(PublishJob)) is None
        assert await session.scalar(select(ReviewJob)) is None


async def test_switch_back_to_review_stops_queued_automatic_publish(clean_database):
    context = await setup_case(clean_database)
    async with clean_database() as session:
        await analyze_post(session, context["post_id"])
        await session.commit()
    async with clean_database() as session:
        policy = await session.get(PublishingSettings, publishing_scope_key(context["tenant_id"]))
        policy.mode = "REVIEW"
        await session.commit()
    async with clean_database() as session:
        publish = await session.scalar(select(PublishJob))
        with pytest.raises(PermissionError):
            await publish_comment_job(session, publish.id)
    assert (await mock_service.get_comments("auto-mode-post", inject_failure=False)).items == []


async def test_publishing_settings_are_persistent_tenant_scoped_and_role_checked(clean_database):
    context = await _seed(clean_database)
    other = await _seed(clean_database)
    settings = get_settings()

    def headers(user_id):
        return {"Authorization": "Bearer " + create_access_token(
            subject=user_id, secret=settings.app_secret_key.get_secret_value(),
            expires_delta=timedelta(minutes=5),
        )}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as client:
        result = await client.patch("/system/publishing-settings", headers=headers(context["user_id"]),
                                    json={"mode": "AUTO", "auto_disclosure_enabled": True})
        assert result.status_code == 200, result.text
        assert result.json()["mode"] == "AUTO"
        assert result.json()["auto_disclosure_enabled"] is True
        assert not next(item for item in result.json()["platform_readiness"] if item["platform"] == "DOUYIN")["automatic_publish_available"]
        other_result = await client.get("/system/publishing-settings", headers=headers(other["user_id"]))
        assert other_result.json()["mode"] == "REVIEW"
        bad = await client.patch("/system/publishing-settings", headers=headers(context["user_id"]), json={"mode": None})
        assert bad.status_code == 422
        async with clean_database() as session:
            user = await session.get(User, context["user_id"])
            user.role = UserRole.VIEWER
            await session.commit()
        forbidden = await client.patch("/system/publishing-settings", headers=headers(context["user_id"]), json={"mode": "REVIEW"})
        assert forbidden.status_code == 403

