# Xiaohongshu Adapter Capabilities

Documentation checked: 2026-09-19. Source status: awaiting written official or formal partner verification of comment publishing. No live account or sending test was performed.

| Adapter capability | Status | Scope / limitation |
|---|---|---|
| `creator_monitoring` | `UNKNOWN` | Arbitrary creator monitoring is unverified |
| `new_post_webhook` | `UNKNOWN` | Unverified |
| `latest_posts` | `UNKNOWN` | Unverified |
| `post_fetch` | `UNKNOWN` | Third-party post access is unverified |
| `comment_read` | `UNKNOWN` | Third-party comment read is unverified |
| `top_level_comment` | `UNKNOWN` | Third-party top-level comment is unverified |
| `comment_reply` | `UNKNOWN` | Unverified; never substituted for top-level comment |
| `comment_delete` | `UNKNOWN` | Unverified |
| `comment_created_at` | `UNKNOWN` | Unverified |
| `chronological_rank` | `UNKNOWN` | Unverified |
| `visible_rank` | `UNKNOWN` | Unverified and never estimated as exact |
| `ai_disclosure` | `UNKNOWN` | Must be resolved before automated publishing |

All operations fail closed. No browser, emulator, scraping, device automation, or private API exists in this adapter.

The official [OAuth Scope documentation](https://openaccount.xiaohongshu.com/docs/scope) currently lists `basic_info` as the initial open scope; note read/write capabilities are listed as planned. The [API directory](https://openaccount.xiaohongshu.com/docs/api-reference) documents authorization and account identity operations, not top-level comment creation. These sources do not establish automatic commenting permission for own, partner, or third-party notes, and an account login token cannot be treated as such evidence.

`get_integration_status()` explicitly returns `configured=false`, `top_level_publish_configured=false`, and `TOP_LEVEL_COMMENT_UNVERIFIED`, even if an arbitrary client object is supplied. A future official integration needs documented operation, granted application/account scope, account-bound credentials, expiry, and a supported way to verify uncertain outcomes before this status can change.

The absence of an established public comment API does not prove ordinary users cannot comment through the website. Normal visible UI interaction is assessed separately in [the browser assessment](../../../../docs/browser-publishing-research-2026-09-19.md); no real browser sending is implemented in this adapter.
