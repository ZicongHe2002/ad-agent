from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.enums import CreatorRelationship, Platform, UserRole
from app.main import app
from app.models import AuditLog, Brand, Campaign, Creator, Post, Tenant, User


@pytest_asyncio.fixture
async def api_case(clean_database):
    async with clean_database() as session, session.begin():
        tenant = Tenant(name="API regressions", slug="api-regressions")
        other = Tenant(name="Other tenant", slug="other-tenant")
        session.add_all([tenant, other])
        await session.flush()
        users = {
            role.value: User(tenant_id=tenant.id, role=role, email=f"{role.value.lower()}@example.com",
                             display_name=role.value, password_hash="unused-in-token-tests")
            for role in UserRole
        }
        users["GLOBAL"] = User(role=UserRole.ADMIN, email="global@example.com", display_name="Global", password_hash="unused")
        users["UNSCOPED"] = User(role=UserRole.VIEWER, email="unscoped@example.com", display_name="Unscoped", password_hash="unused")
        brand = Brand(tenant_id=tenant.id, name="Brand")
        other_brand = Brand(tenant_id=other.id, name="Other Brand")
        session.add_all([*users.values(), brand, other_brand])
        await session.flush()
        campaign = Campaign(brand_id=brand.id, name="Campaign")
        creator = Creator(tenant_id=tenant.id, name="Creator", category="Fashion", relationship_type=CreatorRelationship.PARTNER_CREATOR)
        other_creator = Creator(tenant_id=other.id, name="Other Creator", category="Fashion", relationship_type=CreatorRelationship.PARTNER_CREATOR)
        session.add_all([campaign, creator, other_creator])
        await session.flush()
        posts = [Post(platform=Platform.MOCK, creator_id=item.id, external_post_id=f"post-{index}", raw_payload_hash="a" * 64,
                      published_at=utc_now(), detected_at=utc_now()) for index, item in enumerate([creator, other_creator])]
        session.add_all(posts)
        await session.flush()
        ids = {"brand": str(brand.id), "other_brand": str(other_brand.id), "campaign": str(campaign.id),
               "creator": str(creator.id), "post": str(posts[0].id), "other_post": str(posts[1].id), "tenant": tenant.id}
        settings = get_settings()
        headers = {name: {"Authorization": "Bearer " + create_access_token(
            subject=user.id, secret=settings.app_secret_key.get_secret_value(),
            expires_delta=timedelta(minutes=5), algorithm=settings.jwt_algorithm,
        )} for name, user in users.items()}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as client:
        yield client, headers, ids, clean_database


async def test_campaign_patch_preserves_loaded_defaults_and_audits_tenant(api_case):
    client, headers, ids, factory = api_case
    result = await client.patch(f"/campaigns/{ids['campaign']}", json={"name": "Updated"}, headers=headers["BRAND_MANAGER"])
    assert result.status_code == 200, result.text
    assert result.json()["updated_at"]
    async with factory() as session:
        campaign = await session.get(Campaign, UUID(ids["campaign"]))
        assert campaign.name == "Updated"
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == "campaign.update"))
        assert audit.tenant_id == ids["tenant"]
        assert audit.before["name"] == "Campaign"
        assert audit.after["name"] == "Updated"


@pytest.mark.parametrize("role", ["BRAND_MANAGER", "REVIEWER", "VIEWER"])
async def test_campaign_kill_switch_admin_only_and_no_partial_write(api_case, role):
    client, headers, ids, factory = api_case
    response = await client.patch(f"/campaigns/{ids['campaign']}", json={"name": "Not allowed", "publisher_kill_switch": True}, headers=headers[role])
    assert response.status_code == 403
    async with factory() as session:
        campaign = await session.get(Campaign, UUID(ids["campaign"]))
        assert not campaign.publisher_kill_switch
        assert campaign.name == "Campaign"


async def test_campaign_admin_kill_switch_returns_success(api_case):
    client, headers, ids, _ = api_case
    response = await client.patch(f"/campaigns/{ids['campaign']}", json={"publisher_kill_switch": True}, headers=headers["ADMIN"])
    assert response.status_code == 200, response.text
    assert response.json()["publisher_kill_switch"] is True


@pytest.mark.parametrize("role", ["ADMIN", "BRAND_MANAGER", "REVIEWER", "VIEWER"])
async def test_global_publisher_control_not_available_to_tenant_users(api_case, role):
    client, headers, _, _ = api_case
    response = await client.post("/system/publishers/MOCK/disable", headers=headers[role])
    assert response.status_code == 403


async def test_global_admin_can_disable_publisher(api_case):
    client, headers, _, _ = api_case
    response = await client.post("/system/publishers/MOCK/disable", headers=headers["GLOBAL"])
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", ["/posts", "/creators", "/brands", "/campaigns", "/metrics/overview"])
async def test_tenantless_non_admin_is_denied(api_case, path):
    client, headers, _, _ = api_case
    response = await client.get(path, headers=headers["UNSCOPED"])
    assert response.status_code == 403


async def test_post_read_scope_and_global_admin(api_case):
    client, headers, ids, _ = api_case
    result = await client.get("/posts", headers=headers["VIEWER"])
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["id"] == ids["post"]
    assert (await client.get(f"/posts/{ids['other_post']}", headers=headers["VIEWER"])).status_code == 404
    assert (await client.get("/posts", headers=headers["GLOBAL"])).json()["total"] == 2


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=-1", "limit=501"])
async def test_invalid_pagination_is_rejected(api_case, query):
    client, headers, _, _ = api_case
    response = await client.get(f"/brands?{query}", headers=headers["VIEWER"])
    assert response.status_code == 422


async def test_pagination_total_is_not_page_size(api_case):
    client, headers, _, _ = api_case
    response = await client.get("/brands?limit=1&offset=1", headers=headers["GLOBAL"])
    assert len(response.json()["items"]) == 1
    assert response.json()["total"] == 2


@pytest.mark.parametrize("changes", [
    {"max_comments_per_day": 1, "max_comments_per_creator_per_day": 2},
    {"name": None}, {"human_review_required": None},
    {"start_at": "2026-02-01T00:00:00Z", "end_at": "2026-01-01T00:00:00Z"},
])
async def test_campaign_patch_validates_merged_resource(api_case, changes):
    client, headers, ids, _ = api_case
    response = await client.patch(f"/campaigns/{ids['campaign']}", json=changes, headers=headers["ADMIN"])
    assert response.status_code == 422, response.text


async def test_creator_interval_patch_does_not_commit_invalid_state(api_case):
    client, headers, ids, _ = api_case
    response = await client.patch(f"/creators/{ids['creator']}", json={"hot_poll_interval_sec": 100}, headers=headers["BRAND_MANAGER"])
    assert response.status_code == 422, response.text


async def test_creator_accounts_are_persisted_and_returned(api_case):
    client, headers, _, _ = api_case
    response = await client.post("/creators", headers=headers["BRAND_MANAGER"], json={
        "name": "Another", "category": "Fashion", "platform_accounts": [{"platform": "MOCK", "external_creator_id": "creator-api"}],
    })
    assert response.status_code == 201, response.text
    listed = (await client.get("/creators?platform=MOCK", headers=headers["VIEWER"])).json()
    assert listed["total"] == 1
    assert listed["items"][0]["platform_accounts"][0]["external_creator_id"] == "creator-api"


async def test_product_claim_create_approve_revoke_and_decimal_update(api_case):
    client, headers, ids, _ = api_case
    product = await client.post("/products", headers=headers["BRAND_MANAGER"], json={
        "brand_id": ids["brand"], "name": "Coat", "category": "Fashion", "price_min": 50, "price_max": 100,
    })
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]
    invalid = await client.patch(f"/products/{product_id}", headers=headers["BRAND_MANAGER"], json={"price_min": 200})
    assert invalid.status_code == 422
    updated = await client.patch(f"/products/{product_id}", headers=headers["BRAND_MANAGER"], json={"price_min": 60})
    assert updated.status_code == 200, updated.text
    claim = await client.post(f"/products/{product_id}/claims", headers=headers["BRAND_MANAGER"], json={"claim_text": "Made from wool", "evidence": {"source": "material report"}})
    assert claim.status_code == 201, claim.text
    assert claim.json()["status"] == "DRAFT"
    path = f"/products/{product_id}/claims/{claim.json()['id']}"
    assert (await client.post(path + "/approve", headers=headers["BRAND_MANAGER"])).json()["status"] == "APPROVED"
    assert (await client.post(path + "/revoke", headers=headers["BRAND_MANAGER"])).json()["status"] == "REJECTED"


@pytest.mark.parametrize("claim_input", [
    {"claim_text": "No evidence"},
    {"claim_text": "Expired", "evidence": {"source": "report"}, "expires_at": "2020-01-01T00:00:00Z"},
])
async def test_claim_approval_requires_current_evidence(api_case, claim_input):
    client, headers, ids, _ = api_case
    product = (await client.post("/products", headers=headers["ADMIN"], json={"brand_id": ids["brand"], "name": "Coat", "category": "Fashion"})).json()
    claim = (await client.post(f"/products/{product['id']}/claims", headers=headers["ADMIN"], json=claim_input)).json()
    response = await client.post(f"/products/{product['id']}/claims/{claim['id']}/approve", headers=headers["ADMIN"])
    assert response.status_code == 422


async def test_duplicate_resource_returns_safe_conflict(api_case):
    client, headers, ids, _ = api_case
    response = await client.post("/campaigns", headers=headers["ADMIN"], json={"brand_id": ids["brand"], "name": "Campaign"})
    assert response.status_code == 409, response.text
    assert "INSERT INTO" not in response.text
