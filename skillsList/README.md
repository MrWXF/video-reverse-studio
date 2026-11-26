# 从设计到发布维护的 Skills 推荐清单

> 生成日期：2026-11-26  
> 目标：按软件生命周期整理一套可直接落地的 Agent Skills 组合，覆盖需求发现、设计、架构、开发、内容生成、测试、安全、发布、运维和维护。  
> 检索范围：本地已克隆的 GitHub 仓库、当前 Codex 内置 Skills、官方精选仓库入口。

## 结论先行

不建议“看到就装”。推荐用 **一条主链路 + 按需插件** 的方式采用：

```text
office-hours
  → spec
  → plan-eng-review
  → plan-design-review
  → design-review
  → review-agent
  → qa / qa-only
  → cso
  → ship
  → land-and-deploy
  → canary
  → investigate / health
  → retro / learn
```

如果只想安装最少的一组，优先选择：

| 阶段 | 最少推荐 | 解决的问题 |
| --- | --- | --- |
| 发现与设计 | `office-hours`、`plan-design-review`、`design-review` | 先想清楚值不值得做，再让设计与实现保持一致 |
| 规格与架构 | `spec`、`plan-eng-review` | 把模糊想法变成可执行规格、架构和测试计划 |
| 开发与生成 | `review-agent`、`skill-creator`、`imagegen` | 代码审查、定制项目 Skill、生成视觉素材 |
| 测试与安全 | `qa-only`、`cso` | 浏览器验收、缺陷报告、OWASP/STRIDE 安全检查 |
| 发布 | `ship`、`land-and-deploy`、`canary` | 发布前检查、合并部署、上线后监控 |
| 运维与维护 | `investigate`、`health`、`document-generate`、`retro` | 根因排查、质量盘点、文档同步、复盘沉淀 |

## 推荐等级

| 等级 | 含义 | 使用建议 |
| --- | --- | --- |
| **S** | 核心 | 大多数产品研发团队都应采用，优先纳入工作流 |
| **A** | 推荐 | 在对应场景收益明显，按团队规模选用 |
| **B** | 可选 | 特定技术栈或特定阶段使用，避免默认全装 |

## 分类索引

| 文档 | 覆盖阶段 | 主要内容 |
| --- | --- | --- |
| [01-discovery-and-design.md](01-discovery-and-design.md) | 需求发现、产品与视觉设计 | 产品取舍、设计系统、视觉评审、可用性测试 |
| [02-architecture-and-planning.md](02-architecture-and-planning.md) | 规格、架构、计划 | 可执行规格、工程评审、DX 评审、自动评审流水线 |
| [03-development-and-generation.md](03-development-and-generation.md) | 开发、内容与资产生成 | 安全护栏、第二意见、Skill 定制、MCP 与 Docker |
| [04-testing-and-security.md](04-testing-and-security.md) | 测试、质量、安全 | 浏览器 QA、性能基线、PR 审查、安全审查 |
| [05-release-and-deployment.md](05-release-and-deployment.md) | 发布、部署 | 发布门禁、部署配置、合并上线、金丝雀监控 |
| [06-operations-and-maintenance.md](06-operations-and-maintenance.md) | 运维、维护、复盘 | 根因排查、健康度、文档生成、经验沉淀 |
| [07-ai-media-and-integrations.md](07-ai-media-and-integrations.md) | AI 媒体与外部集成 | 图像、视频、语音、搜索、MCP、页面智能体 |
| [SOURCES.md](SOURCES.md) | 来源与核验 | 仓库、版本、许可证、在线复核状态、排除项 |

## 三套来源如何组合

### 1. Codex 原生基线

来源：`C:\Users\Administrator\.codex\skills\.system`

- `skill-installer`：从官方精选仓库或其他 GitHub 仓库安装 Skill。
- `skill-creator`：把团队自己的发布、回滚、值班、设计规范固化为 Skill。
- `review-agent`：只读缺陷审查，适合 PR 前的第二道检查。
- `imagegen`：生成或编辑位图素材，适合海报、插画、UI 概念图和占位素材。

这组 Skill 与当前 Codex 环境兼容性最好，应作为基线。

### 2. gstack 完整研发流水线

来源：`D:\project\github\gstack`  
上游：`https://github.com/garrytan/gstack`  
本地快照：`a6fb31726cece1d1bba401fde593db7cb96bc738`（2026-05-26）  
许可证：MIT

gstack 的价值不是单个 Skill，而是把 **Think → Plan → Build → Review → Test → Ship → Reflect** 串成流水线。每个阶段的产出会成为下一阶段的输入，适合从 0 到 1 或需要稳定交付节奏的产品。

注意：gstack 主要面向 Claude Code，使用 Slash Command、`AskUserQuestion`、Claude 风格 hooks 和配套脚本。迁移到 Codex 时应按“流程模板”使用，并逐项检查：

1. Skill 是否依赖特定命令或 MCP 工具；
2. hooks 是否需要改写或删除；
3. 脚本依赖是否已安装；
4. Slash Command 是否改成自然语言指令或 Codex 自定义命令；
5. 是否会把代码、日志或密钥发送给外部服务。

### 3. hermes-agent 可选能力

来源：`D:\project\github\hermes-agent\optional-skills`  
上游：`https://github.com/NousResearch/hermes-agent`  
本地快照：`6fdbf2f2d76cf37393e657bf37ceda3d84589200`（2026-04-23）  
仓库许可证：MIT；抽查的推荐 Skill 也标注 MIT

hermes 的 optional-skills 很广，不应全部纳入研发流程。本清单只选与通用研发相关的 DevOps、MCP、UX 测试、研究和媒体能力，排除区块链、医疗、健身、通信、邮件等垂直或高风险类别。

## 采用路线

### 第一阶段：先建立最小闭环

适合个人开发者或 1～3 人小组：

1. `office-hours`：确认问题、目标用户和不做的范围。
2. `spec`：把结论写成可执行规格。
3. `plan-eng-review`：锁定架构、数据流、边界和测试计划。
4. `design-review`：在实现后做视觉一致性检查。
5. `review-agent`：做只读缺陷审查。
6. `qa-only`：从用户路径做浏览器验收，先报告不自动改代码。
7. `ship`：发布前检查、提交、推送和建立 PR。
8. `investigate`：上线问题的根因排查。
9. `retro`、`learn`：复盘并沉淀项目经验。

### 第二阶段：补齐团队治理

- `plan-design-review`：设计评审前置，减少返工。
- `plan-devex-review`、`devex-review`：优化新人和外部开发者的接入体验。
- `cso`：安全评审。
- `benchmark`：建立性能基线并监控回归。
- `setup-deploy`、`land-and-deploy`、`canary`：标准化部署和上线监控。
- `context-save`、`context-restore`：长任务中断后的上下文恢复。
- `guard`、`freeze`：限制破坏性命令和编辑范围。

### 第三阶段：按产品类型扩展

- AI 图像/视频产品：`imagegen`、`stable-diffusion`、`inference-sh-cli`。
- 语音和转写产品：`whisper`。
- 需要对外提供工具的平台：`fastmcp`、`mcporter`、`page-agent`。
- 研究密集型产品：`duckduckgo-search`、`parallel-cli`、`qmd`。
- 容器化部署：`docker-management`。

## 不要默认安装的 Skill

- `autoplan`：会连续运行 CEO、设计、工程、DX 四类评审，适合高成熟度团队；小任务容易过度设计。
- `design-shotgun`：需要多轮方案生成和人工选择，适合视觉探索阶段，不适合每次小改版。
- `plan-tune`：属于个性化提问调优，团队统一流程中收益有限。
- `landing-report`：只读发布队列面板，只有在使用 gstack 的多版本队列时才需要。
- 来源不明的“全能”Skill：通常包含广泛工具权限、外部遥测或不可审计脚本，必须先做供应链检查。

## 兼容性与风险

1. **不是所有 Skill 都能直接复制到 Codex。** Skill 的 `SKILL.md` 格式相近，但工具名、hooks、Slash Command 和运行环境可能不同。
2. **Skill 不是权限沙箱。** 一个 Skill 能执行什么，最终取决于 Agent 的工具权限；执行前应检查外部请求、密钥读取、文件删除和部署命令。
3. **浏览器类 Skill 需要真实运行环境。** `browse`、`qa`、`benchmark`、`adversarial-ux-test` 依赖浏览器、Playwright 或 daemon，必须在本机验证。
4. **第三方服务会产生费用与数据风险。** `inference-sh-cli`、`parallel-cli`、稳定扩散推理、语音转写等需要 API Key、GPU 或云服务；先确认数据留存和费用上限。
5. **许可证要逐个核验。** 仓库级 MIT 不自动覆盖所有内嵌第三方组件；复制脚本前检查文件头和依赖许可证。
6. **在线元数据未复核。** 当前环境无法连接 GitHub，本清单不提供 star 数、最新版本排名或下载量；版本以本地 commit 为准。

## 检索与更新方法

复查 gstack 本地 Skill：

```powershell
Get-ChildItem 'D:\project\github\gstack' -Recurse -Filter SKILL.md
```

复查 hermes 可选 Skill：

```powershell
Get-ChildItem 'D:\project\github\hermes-agent\optional-skills' -Recurse -Filter SKILL.md
```

安装官方精选 Skill 时，优先通过 `skill-installer`，不要手工复制来历不明的脚本：

```text
请使用 skill-installer，从 openai/skills 的 curated 目录列出并安装适合当前项目的 Skill。
```

官方精选入口：`https://github.com/openai/skills/tree/main/skills/.curated`

## 推荐落地原则

- **每个阶段只保留一个主 Skill。** 例如设计阶段主用 `plan-design-review`，视觉验收主用 `design-review`，不要让多个相似 Skill 同时决策。
- **先只读，再自动修改。** 优先用 `qa-only`、`review-agent` 发现问题，确认后再让可写 Skill 修复。
- **把团队规则写成自己的 Skill。** 发布清单、回滚步骤、SLO、接口规范、设计 token 和值班流程，都比通用 Skill 更值得固化。
- **每次引入新 Skill 都做一次小范围演练。** 用真实仓库的小改动验证权限、产物、成本和回滚。

