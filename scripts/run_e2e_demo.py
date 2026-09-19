#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any
from uuid import uuid4

import httpx


async def _wait_for(client: httpx.AsyncClient, description: str, timeout_seconds: float, probe):
    deadline = time.monotonic() + timeout_seconds
    last: Any = None
    while time.monotonic() < deadline:
        last = await probe()
        if last is not None:
            return last
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {description}; last response={last!r}")


async def run(
    base_url: str,
    *,
    email: str,
    password: str,
    existing_comments: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        health = await client.get("/api/v1/system/health")
        health.raise_for_status()
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        creators = await client.get("/api/v1/creators", params={"platform": "MOCK"})
        creators.raise_for_status()
        creator = next(
            (item for item in creators.json()["items"] if item["name"] == "羊绒穿搭示例"),
            None,
        )
        if creator is None:
            raise RuntimeError("Run scripts/seed_demo.py before the distributed demo")

        external_post_id = f"demo-post-{uuid4()}"
        created = await client.post(
            "/api/v1/mock/posts",
            json={
                "external_creator_id": "mock-creator-yangrong",
                "external_post_id": external_post_id,
                "title": "奶油白羊绒大衣的秋冬搭配",
                "caption": "用深棕围巾和直筒裤压住奶油白的轻盈感。",
                "hashtags": ["羊绒", "秋冬穿搭"],
            },
        )
        created.raise_for_status()
        if existing_comments:
            simulated = await client.post(
                f"/api/v1/mock/posts/{external_post_id}/simulate-comments",
                json={"count": existing_comments, "interval_ms": 1},
            )
            simulated.raise_for_status()

        poll = await client.post(f"/api/v1/creators/{creator['id']}/poll-now")
        poll.raise_for_status()

        async def find_post():
            response = await client.get("/api/v1/posts", params={"creator_id": creator["id"]})
            response.raise_for_status()
            return next(
                (
                    item
                    for item in response.json()["items"]
                    if item["external_post_id"] == external_post_id
                ),
                None,
            )

        post = await _wait_for(client, "monitor detection", timeout_seconds, find_post)

        async def find_review():
            response = await client.get("/api/v1/review/jobs", params={"status": "PENDING"})
            response.raise_for_status()
            for item in response.json()["items"]:
                detail = await client.get(f"/api/v1/review/jobs/{item['id']}")
                detail.raise_for_status()
                payload = detail.json()
                if payload.get("candidate", {}).get("post_id") == post["id"]:
                    return payload
            return None

        review = await _wait_for(client, "candidate review", timeout_seconds, find_review)
        approval = await client.post(
            f"/api/v1/review/jobs/{review['id']}/approve",
            json={
                "notes": "Approved by deterministic end-to-end demo",
                "disclosure_status": "DECLARED",
                "disclosure_evidence": {
                    "source": "mock-demo-policy",
                    "note": "Mock official identity and disclosure control confirmed for this demo",
                },
            },
        )
        approval.raise_for_status()

        async def find_published():
            response = await client.get("/api/v1/comments/published", params={"platform": "MOCK"})
            response.raise_for_status()
            return next(
                (item for item in response.json()["items"] if item["post_id"] == post["id"]),
                None,
            )

        published = await _wait_for(
            client, "official Mock publish", timeout_seconds, find_published
        )
        timeline_response = await client.get(f"/api/v1/posts/{post['id']}/timeline")
        timeline_response.raise_for_status()
        result = {
            "status": "PUBLISHED",
            "post": post,
            "review_job_id": review["id"],
            "published_comment": published,
            "expected_rank": existing_comments + 1,
            "rank_matches": published["chronological_rank"] == existing_comments + 1,
            "top5": published["chronological_rank"] <= 5,
            "timeline": timeline_response.json()["events"],
        }
        if not result["rank_matches"]:
            raise AssertionError(json.dumps(result, ensure_ascii=False))
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="firstcomment-demo")
    parser.add_argument("--existing-comments", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            args.base_url,
            email=args.email,
            password=args.password,
            existing_comments=args.existing_comments,
            timeout_seconds=args.timeout,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
