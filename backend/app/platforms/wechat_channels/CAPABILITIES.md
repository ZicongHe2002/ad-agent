# WeChat Channels Adapter Capabilities

Baseline date: 2026-09-02. Source status: awaiting written official or formal partner verification.

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
