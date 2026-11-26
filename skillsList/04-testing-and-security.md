# 04 测试、质量与安全

目标：用“静态审查 + 自动化测试 + 真实浏览器路径 + 安全审查 + 性能基线”形成发布前的质量证据。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用时机 |
| --- | --- | --- | --- |
| S | `qa-only` | 报告式 QA，不修改代码 | 每轮功能完成、发布前 |
| S | `qa` | 系统 QA、修复缺陷并补回归测试 | 已授权自动修复时 |
| S | `browse` | 无头浏览器访问、点击、截图和页面验证 | 需要真实 UI 路径时 |
| S | `cso` | OWASP Top 10 + STRIDE 安全审查 | 处理认证、支付、上传、权限时 |
| S | `review` | 发布前 PR 审查 | 合并前 |
| A | `review-agent` | 只读缺陷优先审查 | 提交前、PR 前 |
| A | `benchmark` | 页面加载、Core Web Vitals、资源体积回归 | 性能敏感产品、每次发布 |
| A | `adversarial-ux-test` | 困难用户视角的可用性测试 | 关键流程上线前 |
| A | `1password` | 通过 CLI 注入密钥，避免明文写入命令 | 需要访问测试或部署环境 |
| B | `oss-forensics` | 开源仓库供应链取证与异常调查 | 怀疑依赖被篡改、删除提交或强推 |

## 测试分层

| 层级 | 目标 | 推荐工具/Skill | 是否每次发布 |
| --- | --- | --- | --- |
| 静态审查 | 逻辑、边界、可维护性 | `review-agent`、`review` | 是 |
| 单元测试 | 纯函数、服务、解析、权限判断 | 项目测试框架 | 是 |
| 集成测试 | API、数据库、外部服务契约 | 项目测试框架 | 是 |
| 端到端测试 | 用户主路径 | `browse`、`qa-only` | 是 |
| 视觉验收 | 布局、层级、响应式、状态 | `design-review` | 是 |
| 可用性测试 | 新手、抗拒技术用户、误操作 | `adversarial-ux-test` | 关键版本 |
| 性能回归 | 首屏、资源、交互延迟 | `benchmark` | 性能敏感版本 |
| 安全审查 | 认证、授权、注入、数据暴露 | `cso` | 涉及敏感面时，至少每版本 |
| 供应链检查 | 依赖、提交历史、发布完整性 | `oss-forensics` | 异常时或高安全项目 |

## 逐项说明

### `qa-only`（S）

来源：gstack，`D:\project\github\gstack\qa-only\SKILL.md`。

用途：按 QA 方法论测试 Web 应用，只报告问题，不修改代码。适合作为自动修复前的可信基线。

优点：风险低、适合首次引入、便于人工判断问题真伪。

使用建议：提供测试账号、环境地址、关键路径和不可触碰的数据范围。

### `qa`（S）

来源：gstack，`D:\project\github\gstack\qa\SKILL.md`。

用途：测试应用、定位缺陷、用原子提交修复，并尽量生成回归测试。

适合已有测试环境、可回滚分支和明确授权。不要让它在生产环境直接点击、提交表单或修改客户数据。

### `browse`（S）

来源：gstack，`D:\project\github\gstack\browse\SKILL.md`。

用途：快速无头浏览器，用于 QA、截图、点击、导航和站点走查。

前置条件：浏览器运行时、相关依赖和可用网络。若应用依赖登录态，需通过安全方式注入测试会话，不要把真实用户 Cookie 写入仓库。

### `cso`（S）

来源：gstack，`D:\project\github\gstack\cso\SKILL.md`。

用途：以首席安全官视角做 OWASP Top 10 和 STRIDE 威胁建模，强调高置信度发现和具体利用场景。

适合：

- 新增登录、权限、支付、文件上传、Webhook；
- 对外暴露 API；
- 处理个人数据或企业敏感数据。

边界：它是辅助审查，不替代专业渗透测试、合规评估和安全负责人签字。必须人工复核每一条发现。

### `review`（S）

来源：gstack，`D:\project\github\gstack\review\SKILL.md`。

用途：发布前 PR 审查，寻找能通过 CI 但会在生产暴露的问题，并标记完整性缺口。

与 `review-agent` 的区别：`review-agent` 是只读、缺陷优先的工作流；`review` 更偏发布前 PR 视角，可能自动修复明显问题。两者不要在同一 diff 上无序重复执行。

### `review-agent`（A）

来源：Codex 内置，详见 [03-development-and-generation.md](03-development-and-generation.md)。

建议先用它做只读审查，再决定是否进入 `review` 或 `qa` 的自动修复。

### `benchmark`（A）

来源：gstack，`D:\project\github\gstack\benchmark\SKILL.md`。

用途：用浏览器 daemon 建立页面加载、Core Web Vitals 和资源体积基线，比较改动前后差异。

适合前端重、流量大或对转化率敏感的产品。测试环境应尽量固定网络、缓存、数据和设备条件。

### `adversarial-ux-test`（A）

来源：hermes-agent，详见 [01-discovery-and-design.md](01-discovery-and-design.md)。

建议与 `qa-only` 搭配：前者发现“用户是否会困惑”，后者验证“功能是否正确”。

### `1password`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\security\1password\SKILL.md`，MIT。

用途：通过 1Password CLI 读取和注入密钥，避免把密钥写进脚本、命令历史或日志。

安全要求：

- 使用最小权限 Service Account；
- 只在需要的命令中注入；
- 不在输出中打印 secret；
- 定期轮换令牌；
- 不把 `.env` 或 secret 引用提交到仓库。

### `oss-forensics`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\security\oss-forensics\SKILL.md`。

用途：调查开源仓库的删除提交、强推、IOC、供应链异常并生成结构化取证报告。

适合安全事件或高风险依赖审计。日常开发不需要默认启用。

## 推荐测试流程

```text
静态检查
  → 单元/集成测试
  → qa-only（真实浏览器，只报告）
  → 人工确认问题优先级
  → qa（授权后修复 + 回归测试）
  → design-review（视觉）
  → adversarial-ux-test（关键流程）
  → cso（敏感面）
  → benchmark（性能基线）
  → review / review-agent（发布前最终审查）
```

## 发布前质量证据

至少保留：

- 测试命令和执行结果；
- 浏览器验证的页面、账号和关键路径；
- 截图或录屏，尤其是修复前后；
- 已知未修复问题和风险接受人；
- 安全发现及处置结论；
- 性能基线与本次对比；
- 回滚验证结果。

## 常见误区

- 只跑单元测试，不启动真实应用；
- 只验证 happy path，不测空状态、错误、权限和超时；
- 在生产环境做自动点击和表单提交；
- 把 AI 安全报告当作正式渗透测试；
- 只记录“通过”，不保留环境、数据和版本信息；
- 测试数据中包含真实客户隐私。

