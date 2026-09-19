from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.events import event_hub
from app.core.config import get_settings
from app.domain.enums import CapabilityStatus
from app.platforms.base import PublishCommentRequest
from app.platforms.mock.adapter import MockPlatformAdapter
from app.platforms.mock.failure_injection import MockFailureProfile
from app.platforms.registry import platform_registry
from app.platforms.runtime import mock_service
from app.services.comment_service import normalize_comment

router = APIRouter(prefix="/mock", tags=["mock"])
mock_adapter = MockPlatformAdapter(mock_service)
try:
    platform_registry.register(mock_adapter)
except ValueError:
    platform_registry.register(mock_adapter, replace=True)


def mock_only() -> None:
    if get_settings().app_env not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Not found")


class CreatorInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    external_creator_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostInput(BaseModel):
    external_creator_id: str
    external_post_id: str | None = None
    published_at: datetime | None = None
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)


class CommentInput(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    account_id: str = "mock-brand-account"
    idempotency_key: str
    disclosure: str | None = None


class SimulateCommentsInput(BaseModel):
    count: int = Field(ge=0, le=1000)
    interval_ms: int = Field(default=1, ge=0, le=60_000)
    texts: list[str] | None = None


class CapabilityInput(BaseModel):
    statuses: dict[str, CapabilityStatus]


class DemoInput(BaseModel):
    creator_name: str = "羊绒穿搭示例"
    title: str = "奶油白羊绒大衣的秋冬搭配"
    caption: str = "用深棕围巾和直筒裤压住奶油白的轻盈感。"
    existing_comments: int = Field(default=0, ge=0, le=100)


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


@router.post("/creators", dependencies=[Depends(mock_only)], status_code=201)
async def create_creator(body: CreatorInput) -> dict[str, Any]:
    return dump(await mock_service.create_creator(**body.model_dump()))


@router.get("/creators", dependencies=[Depends(mock_only)])
async def list_creators() -> list[dict[str, Any]]:
    return [dump(item) for item in await mock_service.list_creators()]


@router.post("/posts", dependencies=[Depends(mock_only)], status_code=201)
async def create_post(body: PostInput) -> dict[str, Any]:
    post = await mock_service.create_post(**body.model_dump())
    await event_hub.publish(
        "post.detected",
        {
            "platform": "MOCK",
            "post_id": post.external_post_id,
            "creator_id": post.external_creator_id,
        },
    )
    return dump(post)


@router.get("/posts/{post_id}", dependencies=[Depends(mock_only)])
async def get_post(post_id: str) -> dict[str, Any]:
    return dump(await mock_service.get_post(post_id, inject_failure=False))


@router.post("/posts/{post_id}/comments", dependencies=[Depends(mock_only)], status_code=201)
async def publish_comment(post_id: str, body: CommentInput) -> dict[str, Any]:
    receipt = await mock_adapter.publish_top_level_comment(
        PublishCommentRequest(external_post_id=post_id, **body.model_dump())
    )
    chronological, visible = await mock_service.comment_ranks(post_id, receipt.external_comment_id)
    result = dump(receipt)
    result.update(chronological_rank=chronological, visible_rank=visible)
    await event_hub.publish(
        "comment.published",
        {
            "platform": "MOCK",
            "post_id": post_id,
            "external_comment_id": receipt.external_comment_id,
        },
    )
    return result


@router.post("/posts/{post_id}/simulate-comments", dependencies=[Depends(mock_only)])
async def simulate_comments(
    post_id: str, body: SimulateCommentsInput
) -> list[dict[str, Any]]:
    items = await mock_service.simulate_comments(post_id, **body.model_dump())
    return [dump(item) for item in items]


@router.get("/posts/{post_id}/comments", dependencies=[Depends(mock_only)])
async def get_comments(
    post_id: str,
    cursor: str | None = None,
    visible: bool = True,
) -> dict[str, Any]:
    return dump(
        await mock_service.get_comments(post_id, cursor, visible_only=visible, inject_failure=False)
    )


@router.post("/failure-profile", dependencies=[Depends(mock_only)])
async def failure_profile(body: MockFailureProfile) -> dict[str, Any]:
    return dump(await mock_service.configure_failure_profile(body))


@router.post("/capabilities", dependencies=[Depends(mock_only)])
async def capabilities(body: CapabilityInput) -> dict[str, Any]:
    configured = await mock_service.configure_capabilities(**body.statuses)
    return configured.model_dump(mode="json")


@router.post("/reset", dependencies=[Depends(mock_only)])
async def reset() -> dict[str, bool]:
    await mock_service.reset()
    return {"reset": True}


def _anchor(title: str, caption: str) -> str:
    text = f"{title} {caption}".strip()
    for token in ("奶油白", "深棕围巾", "直筒裤", "羊绒大衣"):
        if token in text:
            return token
    chunks = [item for item in re.split(r"[，。！？、\s]+", text) if len(item) >= 2]
    return (chunks[0] if chunks else "帖子中的具体搭配")[:24]


@router.post("/demo", dependencies=[Depends(mock_only)])
async def demo(body: DemoInput) -> dict[str, Any]:
    """Run the deterministic, network-free acceptance flow in one request."""

    await mock_service.reset()
    timeline: list[dict[str, Any]] = []

    async def stage(name: str, **values: Any) -> None:
        timeline.append({"stage": name, **values})
        await event_hub.publish(name, values)

    creator = await mock_service.create_creator(body.creator_name)
    post = await mock_service.create_post(
        creator.external_creator_id, title=body.title, caption=body.caption
    )
    await stage(
        "post.detected", creator_id=creator.external_creator_id, post_id=post.external_post_id
    )
    if body.existing_comments:
        await mock_service.simulate_comments(post.external_post_id, body.existing_comments)

    anchor = _anchor(body.title, body.caption)
    await stage("post.analysis.completed", post_id=post.external_post_id, anchors=[anchor])
    candidates = [
        f"{anchor}这个细节把整体层次拉得很清楚。",
        f"注意到{anchor}的呼应，配色轻但不显单薄。",
    ]
    assert all(anchor in candidate for candidate in candidates)
    assert len({normalize_comment(item) for item in candidates}) == 2
    await stage("comment.generated", post_id=post.external_post_id, candidates=candidates)
    await stage("comment.quality.completed", decision="ALLOW", anchor_coverage=1.0)
    await stage("risk.check.completed", decision="ALLOW", matched_rules=[])

    chosen = candidates[0]
    key = hashlib.sha256(
        f"default\x1fMOCK\x1fmock-brand-account\x1f{post.external_post_id}\x1fdemo\x1fTOP_LEVEL_PRIMARY".encode()
    ).hexdigest()
    receipt = await mock_adapter.publish_top_level_comment(
        PublishCommentRequest(
            external_post_id=post.external_post_id,
            text=chosen,
            account_id="mock-brand-account",
            idempotency_key=key,
            disclosure="BRAND_OFFICIAL",
        )
    )
    chronological_rank, visible_rank = await mock_service.comment_ranks(
        post.external_post_id, receipt.external_comment_id
    )
    await stage(
        "comment.published",
        post_id=post.external_post_id,
        external_comment_id=receipt.external_comment_id,
        chronological_rank=chronological_rank,
        visible_rank=visible_rank,
    )
    return {
        "status": "PUBLISHED",
        "creator": dump(creator),
        "post": dump(post),
        "anchors": [anchor],
        "candidates": candidates,
        "selected_comment": chosen,
        "quality_decision": "ALLOW",
        "risk_decision": "ALLOW",
        "publish_mode": "OFFICIAL_API",
        "receipt": dump(receipt),
        "chronological_rank": chronological_rank,
        "visible_rank": visible_rank,
        "top5": chronological_rank <= 5,
        "timeline": timeline,
    }
