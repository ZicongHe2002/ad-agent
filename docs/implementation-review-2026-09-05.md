# 四份需求文档与实现核查 — 2026-09-05

结论：当前是已有较多业务实现、能通过现有 SQLite 测试的 MVP 开发版本，尚未达到四份文档规定的完成标准。存在数据库启动阻断、安全检查漏洞、运行时接口错误、后台恢复未接入及前端功能未完成，不能仅凭 lint、类型检查和 build 通过判定可交付。

本次核查只读业务代码，新增此报告；没有修复下面的问题，也没有改写原始需求清单。测试仅使用隔离临时数据库。临时 PostgreSQL 实例已关闭。

## 核查范围与实测结果

阅读并对照了 `ENGINEERING_SPEC.md`、`IMPLEMENTATION_ORDER.md`、`NON_GOALS.md`、`PLATFORM_CAPABILITIES.md`，结合后端业务/API/Worker/迁移、前端页面/API 客户端、Compose 与测试代码进行检查。

| 检查 | 本次结果 | 证据边界 |
|---|---|---|
| 后端 Ruff | 通过 | `.venv/bin/ruff check backend` |
| 后端 mypy | 通过，144 个源文件 | 从 `backend/` 执行 `../.venv/bin/mypy app`，读取该目录配置 |
| 后端 pytest | 155 个测试全部通过 | SQLite；部分 Redis/队列测试使用 FakeRedis 或直接调用服务 |
| 后端覆盖率门槛 | 未通过，67.34% < 80% | `pytest --cov=app` 退出码 1；当前配置还把测试文件本身计入统计 |
| 前端 ESLint / TypeScript / production build | 均通过 | build 使用 WASM SWC fallback；未证明浏览器交互可用 |
| SQLite 空库升级及回滚 | 通过 | `alembic upgrade head` / `downgrade base` |
| SQLite `alembic check` | 未通过 | 报 enum CHECK constraint 差异；需区分反射兼容性与真实模型漂移 |
| PostgreSQL 16.14 空库迁移 | 失败 | `DuplicateTableError: relation "brand_name" already exists` |
| Docker Compose 全栈验收 | 未完成 | 环境没有 Docker；且真实 PostgreSQL 迁移已确认阻断 |
| Playwright / 100 Post 性能验收 | 未完成 | 仓库没有对应测试配置/用例或性能报告 |

本地 Python 为 3.10.5；包声明和 Docker 目标为 Python 3.12+。不能把本轮结果当作生产版本 Python、真实 Redis、多进程队列和浏览器的完整验收。

## 必须修复的问题

### R01 · P1 · PostgreSQL 初始迁移无法执行

- 位置：`backend/app/models/campaign.py:25`、`backend/app/models/product.py:27`；初始迁移第 857、1167 行。
- 两个表均显式命名唯一约束为 `brand_name`。PostgreSQL 对应唯一索引在同一 schema 中重名，第二个表创建失败。
- 已在新建的 PostgreSQL 16.14 实例实际执行 `alembic upgrade head`，得到上述 `DuplicateTableError`。SQLite 测试未发现这一差异。
- 影响：README 的 `make migrate` 无法在目标数据库完成，后续 seed 和产品验收被阻断。
- 要求：工程规范 §11.5、§31.2、§35.2；实施顺序 017、043、232、237。
- 修复方向：为两表使用独立、稳定的约束名，同时核对模型与迁移；增加真实 PostgreSQL 空库升级、回滚与重升测试。

### R02 · P1 · 未批准声明可穿过质量检查及人工编辑审批

- 位置：`backend/app/agents/quality_evaluator.py:366`，尤其第 373–378 行；`backend/app/services/orchestration.py:340`。
- 逻辑只检查“整段评论中是否包含任意一条获批声明”，然后据此豁免整段风险语言，没有逐条验证实际产品断言。
- 实测：仅批准“羊绒”，评论为“奶油白搭配很清楚，我们的羊绒大衣保证永久治愈皮肤病。”，并提供帖子支持的“奶油白”锚点；质量检查返回 `ALLOW`、分数 `0.95`、`unsupported_claim_detected=False`。
- 审核服务复现进一步得到 `EDITED_APPROVED` 和 `PublishJob.state=READY`。这不是仅存在于一个未调用辅助函数里的问题。
- 要求：FR-023、§21.2、§22.2、§35.4；NON_GOALS 的真实性与反垃圾边界。
- 修复方向：逐个声明绑定获批事实，禁止以无关获批子串授权其他断言；编辑后重新验证全部声明，补充混合“已批准事实 + 未批准断言”的回归案例。

### R03 · P1 · 人工批准错误地消除了 AI 披露待确认状态

- 位置：`backend/app/services/orchestration.py:392`、`:495`；`backend/app/services/publisher_runtime.py:281`、`:323`。
- 普通 approve 根据 `requires_brand_disclosure` 把状态设置成 `DECLARED` 或 `NOT_REQUIRED`，没有要求明确解决 `requires_ai_disclosure_policy_check`，也没有披露动作/平台回执证据。
- 实测：初始 `REQUIRED_PENDING` 的候选经过普通 approve，变成 `DECLARED / READY / OFFICIAL_API`，随后可发布。手动发布确认也硬编码 `DECLARED`。
- 影响：系统把“人工接受了评论”当成“披露已经完成”，台账无法证明真实披露状态。这一判断基于文档要求，不涉及对具体平台法律义务的判断。
- 要求：§22.5、§24.1、§30.4、E2E-010；NON_GOALS 禁止篡改或隐藏来源标识。
- 修复方向：区分内容审批、品牌身份披露与 AI 披露；保存明确的确认和证据，无法确认时维持 pending 或转手工处理。

### R04 · P1 · Capability Scope 和授权条件没有约束实际路由

- 位置：`backend/app/services/capability_service.py:105`、`backend/app/services/orchestration.py:131`、`backend/app/services/publisher_runtime.py:119`。
- `verify_capability_record()` 能返回账号类型不匹配、目标类型不匹配、缺授权等拒绝，但调用方没有传入实际账号上下文，且仅处理“已过期”，其他拒绝仍沿用原 `SUPPORTED/CONDITIONAL` 状态。
- 已复现“验证返回 `ACCOUNT_TYPE_OUT_OF_SCOPE`，发布路由仍为 `OFFICIAL_API`”的矛盾。
- 当前真实平台顶级评论 adapter 仍保留 UNKNOWN，因此未据此宣称已发生真实平台越权发布；但能力启用后，该路由漏洞会成为实际问题。
- 要求：PLATFORM_CAPABILITIES 的 Global Rules；工程规范 §12、§22.5、§23.3。
- 修复方向：用具体账号、授权、目标类型进行每次操作授权，消费完整判定而非仅状态；快照纳入证据内容和有效期。

### R05 · P1 · 权限与租户过滤存在可复现漏洞

- `backend/app/api/v1/posts.py:29`、`:47`：仅在 `tenant_id != None` 时加过滤。实测一个 `tenant_id=None` 的 VIEWER 请求 `/posts` 得到 200，并读到另一个租户的帖子。应仅允许明确的全局管理员跳过隔离，其余缺租户身份应拒绝访问。
- `backend/app/api/v1/campaigns.py:41`、`:114`：BRAND_MANAGER 可以 PATCH `publisher_kill_switch`。实测虽然响应随后触发 R06 的 500，开关已经成功提交，证明角色检查没有阻止修改。规范 §30.1 明确只有 ADMIN 可修改 Kill Switch。
- `backend/app/api/v1/system.py:115`、`:160`：任何租户 ADMIN 都可修改全局 `(platform, capability)` 记录，影响其他租户。代码已有 `is_global_admin`，控制接口未使用；应明确全局与租户管理员边界后统一执行。
- 修复方向：统一 fail-closed 租户依赖；隔离管理开关字段；增加 VIEWER/REVIEWER/BRAND_MANAGER/ADMIN、空租户和跨租户 API 矩阵测试。

### R06 · P1 · 修改接口会触发 MissingGreenlet，出现“保存了却返回失败”

- 位置：`backend/app/api/v1/campaigns.py:126`、`backend/app/api/utils.py:26`；`backend/app/services/orchestration.py:513`。
- ORM 的 `updated_at` 使用 SQL 表达式更新；更新后同步 `model_dict()` 读取尚需加载的属性，在异步会话外触发隐式 I/O。
- 实测 Campaign PATCH 抛 `MissingGreenlet`，但新事务查询发现修改已持久化。用户看到失败后重试，可能重复执行后续动作。
- 手动发布 `published` 确认的服务路径也复现同类错误，并在接口 commit 之前失败，结果不能正常回填。
- 修复方向：明确刷新/加载响应字段，使用稳定响应 DTO；对真实 HTTP 修改接口断言响应和持久化状态一致。应排查所有相同序列化模式，不只改单个接口。

### R07 · P1 · 后台恢复逻辑没有生产调用者，任务可能永久停留

- 位置：`backend/app/services/maintenance_service.py:131`、`backend/app/workers/scheduler.py:165`、`backend/app/workers/publish_actors.py:17`。
- `run_maintenance_once()` 仅被测试手工调用，没有周期调度调用者，也没有提交后投递返回的 reconciliation IDs。
- 它只扫描旧 `PUBLISHING`，未扫描规范要求的旧 `PUBLISH_UNCERTAIN`。
- 发布 actor 先提交 uncertain 状态，再向 Redis 投递 reconcile；若此时投递失败，`max_retries=0`，又没有扫尾任务，数据库记录将失去后续处理。
- 已过期 ReviewJob 在直接 approve 时也未检查 `expires_at`，已复现仍可批准进入 READY。
- 要求：§29.1、§29.4；实施顺序 215、216。
- 修复方向：周期维护 + 事务 outbox 投递恢复事件 + uncertain/ready 重扫；在审核事务内检查过期，扫尾任务不应是唯一防线。

### R08 · P1 · 前端核心配置与手工发布流程未完成

- `frontend/app/brand/page.tsx:1`、`accounts/page.tsx:1`、`settings/page.tsx:1`、`risk/page.tsx:1` 仍为硬编码展示。添加、管理、保存按钮没有真实 API 行为；Settings 的 Toggle 只修改浏览器 state。
- 前端没有调用 `manual-result`，没有 `WAITING_MANUAL_PUBLISH` 工作列表及复制、打开帖子、披露指引、结果回填流程。后端有接口不等于工作流已交付。
- Identity/Voice API 只有创建入口，缺列表、详情、更新/版本读取；Creator UI 缺创建与编辑，无法从空库完成文档要求的完整配置链。
- 要求：§23.5、§26、§35.3；实施顺序 202–207。
- 修复方向：先补齐账号/身份/Voice/Brand 配置与手工发布，再补浏览器测试；运营页不应以固定数据表示真实状态。

### R09 · P1 · 审核上下文不足，无法完成文档规定的安全判断

- 位置：`backend/app/api/v1/review.py:83`、`frontend/app/review/page.tsx:284`。
- Detail 只返回 candidate、quality、risk、anchors，没有完整 Creator relationship、发布账号身份、Opportunity、已批准声明正文、Capability 证据。页面只展示有限引用信息。
- 只展示被自动选中的一个候选；缺文档要求的候选选择、快捷键、复制和打开帖子能力。
- 要求：§24.3、§26.3、Task 10.4。
- 修复方向：提供完整、版本明确的 Review detail DTO，补齐审核操作并用 Playwright 验证，包含 claim 竞争和失败后的状态恢复。

### R10 · P1 · 运行健康报告与监控调度不满足可靠性要求

- `backend/app/api/v1/system.py:50` 仅查询 DB/Redis；即使 Critical Worker 和 Outbox Relay 全部停止，也能报告 ready。仅 scheduler 写应用层 heartbeat。
- 自适应轮询策略有单元测试，但 `backend/app/workers/monitor_actors.py:62` 没接入 expected publish windows、recent activity 等输入，实际不会按这些配置进入 warm/hot。
- `discovery_service.py` 返回失败时丢失 Retry-After，monitor 将 429 与 auth expired 当一般失败处理；不满足尊重 Retry-After、认证过期暂停的要求。
- 没有文档指定的 `(platform, operation)` circuit breaker；scheduler 对坏成员 UUID 等异常也缺少循环级隔离。
- 要求：§14–15、§29.1–29.2、§32.4；实施顺序 212、214。
- 修复方向：补齐运行时输入、退避协议、平台隔离和健康探针；用真实 Redis/worker 测试，而不是仅测试策略函数。

### R11 · P2 · 再生成功路径在默认 Mock 上不可用

- 位置：`backend/app/services/pipeline_service.py:94`、`:507`；`backend/app/agents/comment_agent.py:355`。
- 重生成沿用同一组确定性锚点/句式，但近期历史包含旧候选，因而命中自身上一次生成的重复内容。
- 实测一个正常 WAITING_REVIEW 案例调用再生，返回 `BLOCKED / COMMENT_GENERATION_HARD_GATE_REJECTED`，新候选数 0，旧 review 已变为 EXPIRED。
- 这不是建议放松去重，而是生成器没有产出新的合规候选，且失败时没有可继续审核的替代路径。
- 要求：§21.4、Task 6.9、regenerate API。
- 修复方向：提供确定性但随再生版本变化的有效候选，并明确失败后旧审核项的保留/替代规则；覆盖再生成功、失败、次数上限。

### R12 · P2 · 指标和性能路径尚不能支撑验收结论

- `pipeline_service.py:383`–`:454` 已完成质量/风险计算后才写 QUALITY_CHECKING、RISK_CHECKING。`api/v1/metrics.py:123` 用这些时间戳计算阶段耗时，会把真实检查时间计入 generation，quality/risk 近乎仅反映写库时间。
- Metrics 缺 fetch、analysis、review 等完整阶段，E2E 从 fetching 算起而不是帖子创建；Campaign metrics（`campaigns.py:168`）仍返回固定零值。
- Prometheus 只抓 `backend-api:8000`（`docs/prometheus.yml:6`），而多数业务计数在其他 worker 进程累积；没有跨进程收集设计，generation/detection histogram 也未完整观测。
- Dashboard 未接 First/Top5/Coverage；终态集合遗漏 BLOCKED。Live 的事件样例有 EXAMPLE DATA 标识，但 active 数和 oldest critical 仍为固定值。
- pipeline 没有完整 MEDIUM/SLOW 执行分支，低置信锚点直接 SKIP；运行模式覆盖值也未一致传入生成上下文。没有 100 Post P95 实测报告。
- 要求：§17–18、§28、Task 9.1–9.5；实施顺序 169–180、238。
- 修复方向：在实际阶段起止处记录耗时；统一指标口径；完成所声明路径后再测 P95，不能从 Mock 同进程测试推断分布式性能。

## 其他应补齐的项

| 项目 | 已确认现状 | 建议 |
|---|---|---|
| Claim 有效期 | 生成与审核查询仅筛 APPROVED + active，未筛 expires_at（pipeline:296，orchestration:300） | 排除已过期、已撤销声明，发布前重检当前证据 |
| 审计 | Identity/Voice/Account/Campaign 多个写接口未记录审计；audit helper 未填 tenant_id | 关键变更和审计同事务，保存 actor、tenant、before/after |
| SSE token | `frontend/lib/sse.ts:49` 401 后仍用旧 token 重连，未接统一 refresh | 与普通 API 共享刷新机制，区分无权限与网络断开 |
| 配置生效 | Compose 只传部分环境变量；LLM/阈值等配置未完整转发，运行时直接构建无 provider 的 Agent | 明确 Mock/真实 provider 工厂和配置契约；测试环境变量确实改变行为 |
| 分页 | `api/utils.py:42` 默认 total 为当前页长度 | 独立 count 查询，返回实际有效 limit |
| 保留期与 DLQ | 没有 retention job；outbox 有 DB DLQ，不能代替所有 actor 的失败持久化 | 补 retention 和关键任务可观察的失败台账 |
| 发布配额并发 | 发布前 count 已发布记录，锁仅针对单 PublishJob；无跨 job 原子配额预留 | 在真实 PostgreSQL/Redis 下验证并发最后一个名额；增加原子预留和发布 token bucket |

最后一项是代码级并发风险判断；本次 PostgreSQL 初始化已被 R01 阻断，因此没有宣称完成真实数据库并发复现。

## 四份文档的完成度判断

| 文档 | 判断 |
|---|---|
| ENGINEERING_SPEC.md | 核心模型、规则、Mock 发布、部分审核和 API 已实现；运行验收、安全完整性、前端配置、恢复与性能 DoD 未满足 |
| IMPLEMENTATION_ORDER.md | 244 项仍全为未勾选，且确有多项缺实现/测试；不能把文件存在等同完成，也不能把未勾选等同全部没写 |
| NON_GOALS.md | 未发现检测规避、验证码/指纹绕过、浏览器自动发布模块；但声明真实性和披露状态的防线存在 R02/R03 漏洞 |
| PLATFORM_CAPABILITIES.md | 初始 UNKNOWN 默认与真实 adapter 骨架方向正确；Scope/条件不能只保存，必须参与每次调用授权，R04 尚不满足 |

不建议给出一个缺乏统一权重的“完成百分比”。当前最准确的状态是：已有可保留的业务基础，但 MVP 验收未通过。

## 建议修复与验收顺序

1. 修复 PostgreSQL 迁移和修改接口序列化错误，保证能启动、能可靠保存。
2. 修复声明、披露、Capability Scope、RBAC/租户隔离；将本报告中的复现变成安全回归测试。
3. 接通维护任务、uncertain 恢复、真实 worker/readiness、429/Auth 处理及配额并发控制。
4. 完成配置、审核和手动发布 UI；再进行真实浏览器全流程测试。
5. 校正指标、完善 Fast/Slow 和性能报告，补真实 PostgreSQL/Redis/队列测试及 CI 门槛，再按证据更新实施清单。

现有静态检查与测试可以这样运行（已有依赖时）：

```bash
source .venv/bin/activate
make lint
make typecheck
make test
```

覆盖率必须另外明确执行，当前 `make test` 不会自动执行该门槛：

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

数据库与分布式验收应在上述阻断修复后，在隔离环境执行文档中的 `docker compose up --build`、迁移、seed、分布式 demo 和 Playwright。现阶段不应把这些命令写成“已全部验证成功”。
