#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionFactory
from app.domain.enums import (
    AccountKind,
    AuthStatus,
    CampaignStatus,
    ClaimStatus,
    CreatorRelationship,
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
    Creator,
    CreatorPlatformAccount,
    Product,
    ProductClaim,
    Tenant,
    User,
    VoiceProfile,
)
from app.platforms.errors import PlatformPermanentError
from app.platforms.runtime import mock_service


async def seed() -> dict[str, str]:
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("The deterministic demo seed is disabled in production")
    email = os.getenv("DEMO_ADMIN_EMAIL", "admin@example.com").lower()
    password = os.getenv("DEMO_ADMIN_PASSWORD", "firstcomment-demo")

    async with AsyncSessionFactory() as session, session.begin():
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo"))
        if tenant is None:
            tenant = Tenant(name="FirstComment Demo", slug="demo")
            session.add(tenant)
            await session.flush()

        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=email,
                display_name="Demo Administrator",
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add(user)

        brand = await session.scalar(
            select(Brand).where(Brand.tenant_id == tenant.id, Brand.name == "云绒")
        )
        if brand is None:
            brand = Brand(
                tenant_id=tenant.id,
                name="云绒",
                description="专注羊绒与克制、具体的秋冬穿搭表达",
            )
            session.add(brand)
            await session.flush()

        identity = await session.scalar(
            select(AccountIdentityProfile).where(
                AccountIdentityProfile.tenant_id == tenant.id,
                AccountIdentityProfile.legal_or_operating_entity == "云绒品牌运营主体",
            )
        )
        if identity is None:
            identity = AccountIdentityProfile(
                tenant_id=tenant.id,
                legal_or_operating_entity="云绒品牌运营主体",
                account_kind=AccountKind.BRAND_OFFICIAL,
                public_identity_text="云绒官方账号",
                may_speak_as_consumer=False,
                may_use_first_person_experience=False,
                requires_brand_disclosure=True,
                requires_ai_disclosure_policy_check=True,
            )
            session.add(identity)

        voice = await session.scalar(
            select(VoiceProfile).where(
                VoiceProfile.brand_id == brand.id,
                VoiceProfile.name == "克制而具体",
                VoiceProfile.version == 1,
            )
        )
        if voice is None:
            voice = VoiceProfile(
                brand_id=brand.id,
                name="克制而具体",
                tone_attributes=["具体", "友好", "不过度商业化"],
                preferred_sentence_length="SHORT",
                emoji_policy={"allowed": False},
                forbidden_phrases=["我买过", "亲测", "回购", "全网最低"],
                approved_examples=["奶油白和深棕的呼应让层次很清楚。"],
                version=1,
            )
            session.add(voice)
        await session.flush()

        account = await session.scalar(
            select(BrandAccount).where(
                BrandAccount.platform == Platform.MOCK,
                BrandAccount.external_account_id == "mock-brand-yunrong",
            )
        )
        if account is None:
            account = BrandAccount(
                brand_id=brand.id,
                platform=Platform.MOCK,
                external_account_id="mock-brand-yunrong",
                display_name="云绒官方",
                account_kind=AccountKind.BRAND_OFFICIAL,
                identity_profile_id=identity.id,
                voice_profile_id=voice.id,
                auto_publish_enabled=False,
                publisher_kill_switch=False,
                auth_status=AuthStatus.VALID,
            )
            session.add(account)

        product = await session.scalar(
            select(Product).where(Product.brand_id == brand.id, Product.name == "经典羊绒大衣")
        )
        if product is None:
            product = Product(
                brand_id=brand.id,
                name="经典羊绒大衣",
                category="服装",
                material="羊绒",
            )
            session.add(product)
            await session.flush()
        claim = await session.scalar(
            select(ProductClaim).where(
                ProductClaim.product_id == product.id,
                ProductClaim.claim_text == "面料成分以商品页标注为准",
            )
        )
        if claim is None:
            from app.core.clock import utc_now

            claim = ProductClaim(
                product_id=product.id,
                claim_text="面料成分以商品页标注为准",
                evidence={"source": "demo catalog"},
                status=ClaimStatus.APPROVED,
                approved_by_user_id=user.id,
                approved_at=utc_now(),
            )
            session.add(claim)

        campaign = await session.scalar(
            select(Campaign).where(Campaign.brand_id == brand.id, Campaign.name == "秋冬羊绒穿搭")
        )
        if campaign is None:
            campaign = Campaign(
                brand_id=brand.id,
                name="秋冬羊绒穿搭",
                run_mode=RunMode.FAST,
                creator_relationship_allowlist=[CreatorRelationship.PARTNER_CREATOR.value],
                max_comments_per_day=20,
                max_comments_per_creator_per_day=3,
                human_review_required=True,
                status=CampaignStatus.ACTIVE,
            )
            session.add(campaign)

        creator = await session.scalar(
            select(Creator).where(
                Creator.tenant_id == tenant.id,
                Creator.name == "羊绒穿搭示例",
            )
        )
        if creator is None:
            creator = Creator(
                tenant_id=tenant.id,
                name="羊绒穿搭示例",
                category="时尚",
                relationship_type=CreatorRelationship.PARTNER_CREATOR,
                priority=100,
                monitor_state=MonitorState.ACTIVE,
            )
            session.add(creator)
            await session.flush()
        creator_account = await session.scalar(
            select(CreatorPlatformAccount).where(
                CreatorPlatformAccount.creator_id == creator.id,
                CreatorPlatformAccount.platform == Platform.MOCK,
            )
        )
        if creator_account is None:
            creator_account = CreatorPlatformAccount(
                creator_id=creator.id,
                platform=Platform.MOCK,
                external_creator_id="mock-creator-yangrong",
            )
            session.add(creator_account)
        await session.flush()

        result = {
            "tenant_id": str(tenant.id),
            "admin_user_id": str(user.id),
            "brand_id": str(brand.id),
            "brand_account_id": str(account.id),
            "campaign_id": str(campaign.id),
            "creator_id": str(creator.id),
            "external_creator_id": creator_account.external_creator_id,
            "email": email,
            "password": password,
        }

    try:
        await mock_service.create_creator(
            "羊绒穿搭示例", external_creator_id="mock-creator-yangrong"
        )
    except PlatformPermanentError as exc:
        if "already exists" not in str(exc):
            raise
    return result


def main() -> None:
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
