from fastapi import APIRouter

from . import events, metrics, publishing_settings, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(publishing_settings.router)
api_router.include_router(events.router)
api_router.include_router(metrics.router)


def include_optional_routers() -> None:
    """Import feature routers after all model modules have initialized."""

    from . import (
        auth,
        brands,
        campaigns,
        comments,
        creators,
        mock,
        platform_accounts,
        posts,
        products,
        review,
    )

    for feature in (
        auth,
        brands,
        products,
        campaigns,
        creators,
        platform_accounts,
        posts,
        comments,
        review,
        mock,
    ):
        api_router.include_router(feature.router)


include_optional_routers()
