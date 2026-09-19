from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import audit_resource, model_dict, paginate
from app.domain.enums import Platform, RunMode
from app.models import CommentCandidate, Creator, Post, PostAnchor, PostContent, TimelineEvent, User

router = APIRouter(prefix="/posts", tags=["posts"])


class ReanalyzeInput(BaseModel):
    mode: RunMode = RunMode.NORMAL


class PostSourceURLInput(BaseModel):
    source_url: HttpUrl


async def _get_post_for_user(
    session: AsyncSession,
    post_id: UUID,
    user: User,
) -> Post:
    statement = select(Post).join(Creator, Creator.id == Post.creator_id).where(Post.id == post_id)
    if not is_global_admin(user):
        statement = statement.where(
            Creator.tenant_id == user.tenant_id, Creator.tenant_id.is_not(None)
        )
    post = await session.scalar(statement)
    if post is None:
        raise LookupError(f"Post {post_id} was not found")
    return post


@router.get("")
async def list_posts(
    creator_id: UUID | None = None,
    platform: Platform | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(Post).join(Creator, Creator.id == Post.creator_id)
    if not is_global_admin(user):
        stmt = stmt.where(Creator.tenant_id == user.tenant_id, Creator.tenant_id.is_not(None))
    if creator_id:
        stmt = stmt.where(Post.creator_id == creator_id)
    if platform:
        stmt = stmt.where(Post.platform == platform)
    stmt = stmt.order_by(Post.published_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.get("/{post_id}")
async def get_post_detail(
    post_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    post = await _get_post_for_user(session, post_id, user)
    content = await session.get(PostContent, post_id)
    anchors = (await session.scalars(select(PostAnchor).where(PostAnchor.post_id == post_id))).all()
    candidates = (
        await session.scalars(select(CommentCandidate).where(CommentCandidate.post_id == post_id))
    ).all()
    return {
        **model_dict(post),
        "content": model_dict(content) if content else None,
        "anchors": [model_dict(item) for item in anchors],
        "candidates": [model_dict(item) for item in candidates],
    }


@router.patch("/{post_id}/source-url")
async def update_post_source_url(
    post_id: UUID, body: PostSourceURLInput,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER", "REVIEWER")),
) -> dict[str, Any]:
    post = await _get_post_for_user(session, post_id, user)
    if body.source_url.username or body.source_url.password or len(str(body.source_url)) > 2048:
        raise HTTPException(status_code=422, detail="Post URLs must not contain credentials and must be at most 2048 characters")
    before = model_dict(post)
    post.source_url = str(body.source_url)
    await audit_resource(session, post, user, "post.source_url", before=before)
    await session.commit()
    return model_dict(post)


@router.post("/{post_id}/reanalyze", status_code=202)
async def reanalyze_post(
    post_id: UUID,
    body: ReanalyzeInput,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER", "REVIEWER")),
) -> dict[str, Any]:
    await _get_post_for_user(session, post_id, user)
    from app.workers.pipeline_actors import analyze_post

    message = analyze_post.send(str(post_id), body.mode.value)
    return {"task_id": message.message_id, "post_id": str(post_id), "mode": body.mode.value}


@router.get("/{post_id}/timeline")
async def post_timeline(
    post_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _get_post_for_user(session, post_id, user)
    items = (
        await session.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.aggregate_id == post_id)
            .order_by(TimelineEvent.occurred_at)
        )
    ).all()
    return {"post_id": str(post_id), "events": [model_dict(item) for item in items]}
