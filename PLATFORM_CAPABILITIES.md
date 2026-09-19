# Platform Capabilities Registry

**基准日期**：2026-09-02

状态定义：

```text
SUPPORTED
CONDITIONAL
AUTH_REQUIRED
MANUAL
UNSUPPORTED
UNKNOWN
RATE_LIMITED
DISABLED
```

## Global Rules

1. `UNKNOWN` 不能在代码中当作 `SUPPORTED`。
2. Reply Comment 不能当作 Top-level Comment。
3. 当前已实现的生产通道在没有官方或正式 Partner Capability 时进入 Manual Workflow。
4. 官方 Adapter 不得在失败后隐式回退到浏览器、模拟器、私有 API 或设备自动化。
5. 每次能力验证必须记录来源、日期、Scope、账号类型和到期时间。

普通登录网页交互正在作为独立发送通道研究，并不以开发者 API 申请为技术前提。它尚未实现，也不能继承官方 API 的能力记录；需要分别核实页面操作、账号范围、平台规则及发送结果。详见 [浏览器评论发送研究](docs/browser-publishing-research-2026-09-19.md)。

## Mock Platform

| Capability | Status | Notes |
|---|---|---|
| Creator Monitoring | SUPPORTED | 完整模拟 |
| New Post Event | SUPPORTED | API/Event |
| Post Fetch | SUPPORTED | 完整模拟 |
| Comment Read | SUPPORTED | 完整模拟 |
| Top-level Comment | SUPPORTED | 完整模拟 |
| Comment Reply | SUPPORTED | 完整模拟 |
| Chronological Rank | SUPPORTED | 精确 |
| Visible Rank | SUPPORTED | 可配置模拟 |

## Douyin

| Capability | Initial Status | Notes |
|---|---|---|
| Authorized Account Video Read | CONDITIONAL | 需要官方应用权限和用户授权 |
| Keyword Video Search | CONDITIONAL | 受关键词、时间范围和 Scope 限制 |
| Comment List | CONDITIONAL | 依接口与授权范围 |
| Comment Reply | CONDITIONAL | 官方文档存在回复能力；需权限/授权 |
| Arbitrary Third-party Top-level Comment | UNKNOWN | 不得根据 Reply 能力推断 |
| New Post Webhook for Arbitrary Creator | UNKNOWN | 未验证 |
| Visible Comment Rank | UNKNOWN | 不得估算为精确值 |

## Xiaohongshu

| Capability | Initial Status | Notes |
|---|---|---|
| Arbitrary Creator Monitoring | UNKNOWN | 等待官方或 Partner 书面确认 |
| New Post Webhook | UNKNOWN | 等待确认 |
| Third-party Comment Read | UNKNOWN | 等待确认 |
| Third-party Top-level Comment | UNKNOWN | 等待确认 |
| Visible Comment Rank | UNKNOWN | 等待确认 |

## WeChat Channels

| Capability | Initial Status | Notes |
|---|---|---|
| Arbitrary Creator Monitoring | UNKNOWN | 等待官方或 Partner 书面确认 |
| New Post Webhook | UNKNOWN | 等待确认 |
| Third-party Comment Read | UNKNOWN | 等待确认 |
| Third-party Top-level Comment | UNKNOWN | 等待确认 |
| Visible Comment Rank | UNKNOWN | 等待确认 |

## Capability Record Template

```yaml
platform: DOUYIN
capability: COMMENT_REPLY
status: CONDITIONAL
verified_at: 2026-09-02
expires_at: null
source_title: "官方文档标题"
source_owner: "平台官方"
scope:
  account_types: []
  target_content_types: []
  authorization_required: true
limitations: []
verified_by: "name"
```
