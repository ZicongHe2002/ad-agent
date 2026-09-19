# Douyin Adapter Capabilities

Documentation checked: 2026-09-19. This is documentation research, not application approval or a live integration test. No account credentials or official transport are configured by default.

| Adapter capability | Status | Source owner | Scope and limitation |
|---|---|---|---|
| `creator_monitoring` | `CONDITIONAL` | Douyin official platform | Authorized account/content only; deployment verification required |
| `new_post_webhook` | `UNKNOWN` | — | No verified arbitrary-creator webhook |
| `latest_posts` | `CONDITIONAL` | Douyin official platform | Authorized account/content only |
| `post_fetch` | `CONDITIONAL` | Douyin official platform | Own account's discovered posts; `video.data` |
| `comment_read` | `CONDITIONAL` | Douyin official platform | Own account's discovered posts; `item.comment` |
| `top_level_comment` | `UNKNOWN` | — | Reply capability is not evidence for this capability |
| `comment_reply` | `CONDITIONAL` | Douyin official platform | Existing comment on the authorized user's own post; `item.comment` |
| `comment_delete` | `UNKNOWN` | — | Not implemented |
| `comment_created_at` | `CONDITIONAL` | Douyin official platform | Only when returned by an authorized read call |
| `chronological_rank` | `UNKNOWN` | — | Not inferred from list ordering |
| `visible_rank` | `UNKNOWN` | — | Never estimated as an exact rank |
| `ai_disclosure` | `UNKNOWN` | — | Must be resolved before automated publishing |

There is no browser, emulator, device automation, scraping, or private-API fallback. `UNKNOWN` always fails before the injected official client is called.

## Official sources and exact scope

- [Authorized account video list](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/account-video-list): `video.list`, application permission and user authorization.
- [Specific video data](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/video-data/): `video.data`, authorized user's public videos.
- [Comment list](https://open.douyin.com/platform/resource/docs/openapi/interaction-management/comment-management-user/comment-list): `item.comment`.
- [Reply to a video comment](https://open.douyin.com/platform/resource/docs/openapi/interaction-management/comment-management-user/video-comment-reply): `item.comment`, only the authorized user's own videos.
- [Keyword-search comment reply](https://open.douyin.com/platform/resource/docs/openapi/search-management/keywords-video-comment-management/comment-reply/): a different `video.search.comment` capability. It is not implemented by this own-account adapter and does not prove top-level commenting permission.

No checked source establishes top-level comment creation on own, partner, or arbitrary third-party videos. A commercial partnership alone does not widen OAuth scope; an independently authorized partner account would still be limited to that account's own supported operations.

## Injection contract

An eventual audited `OfficialDouyinTransport` must hold credentials for one authorization. Construct `DouyinClient(transport, authorization=...)` with that authorization's local `account_id`, platform `external_creator_id`, authorization ID, actual granted scopes, and expiry. The adapter must use the same binding; request metadata cannot choose another credential. Credential rotation creates a new bound client/adapter.

The adapter verifies actual creator IDs and only accepts post IDs observed in a successful authorized discovery response. Reads, replies, and reconciliation cannot silently target a different post owner. Mandatory documented scopes cannot be removed through the optional additional-scope map. A supplied `verified_capabilities` set must come from deployment evidence, not user-controlled request data.

`platform_integration_statuses()` reports transport wiring separately from DB capability evidence. Even an injected official client reports `top_level_publish_configured=false`. Reply timeouts or unclassified write failures become uncertain; matching post/intent receipts are required for confirmed reconciliation. No guessed publish or reconciliation HTTP endpoint is implemented.

Ordinary visible browser interaction is a separate research topic in [the browser assessment](../../../../docs/browser-publishing-research-2026-09-19.md); this adapter never silently falls back to it.
