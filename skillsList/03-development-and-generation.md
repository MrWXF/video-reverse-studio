# 03 开发与内容生成

目标：在明确规格和架构后，安全地完成代码、配置、文档与内容资产的生产，并保持可审查、可回滚。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用时机 |
| --- | --- | --- | --- |
| S | `review-agent` | 只读、缺陷优先的代码审查 | 每次提交前或 PR 前 |
| S | `skill-creator` | 把团队流程和领域知识固化为 Codex Skill | 发现重复工作或缺少标准流程时 |
| S | `skill-installer` | 从官方精选或 GitHub 安装 Skill | 引入外部 Skill 时 |
| A | `guard` | 破坏性命令告警 + 目录级编辑限制 | 高风险仓库、生产配置修改 |
| A | `careful` | 对危险命令给出告警 | 日常开发的最低安全护栏 |
| A | `freeze` | 把编辑范围锁定到指定目录 | 大规模仓库、多人并行 |
| A | `context-save` / `context-restore` | 保存或恢复开发上下文 | 长任务、跨会话开发 |
| A | `docker-management` | 容器、镜像、卷、网络和 Compose 管理 | 容器化开发与部署 |
| A | `codex` | 引入第二模型/第二代理做架构或代码挑战 | 重大方案或高风险改动 |
| A | `fastmcp` | 构建和部署 MCP Server | 需要把 API、数据库或内部能力暴露给 Agent 时 |
| B | `page-agent` | 给 Web 产品嵌入页面内自然语言操作 Agent | SaaS、后台、B2B 工具 |
| B | `mcporter` | 列出、配置、调用和生成 MCP 客户端类型 | 多 MCP 服务联调 |

## 逐项说明

### `review-agent`（S）

来源：Codex 内置，`C:\Users\Administrator\.codex\skills\.system\review-agent\SKILL.md`。

用途：对未提交改动、分支 diff、单个 commit 或指定审查要求执行只读缺陷审查。它不应修改文件、提交、推送或发布评论。

适合：

- 开发完成后、提交前的第一轮审查；
- 让审查者专注“作者会修的真实缺陷”；
- 在自动化 QA 前发现逻辑和边界问题。

使用建议：明确审查基线，例如“审查当前未提交改动”或“审查相对 main 的 diff”，并要求只报告可复现、可定位的问题。

### `skill-creator`（S）

来源：Codex 内置，`C:\Users\Administrator\.codex\skills\.system\skill-creator\SKILL.md`。

用途：创建或更新 Codex Skill，把以下团队知识变成可复用流程：

- 发布与回滚手册；
- 数据库迁移规范；
- 设计 token 和页面验收标准；
- 安全编码清单；
- 故障排查树；
- 日志、指标和告警约定。

这是中后期收益最高的 Skill。通用 Skill 只能提供方法，团队专属的“什么时候算完成、出问题找谁、如何回滚”必须自己沉淀。

### `skill-installer`（S）

来源：Codex 内置，`C:\Users\Administrator\.codex\skills\.system\skill-installer\SKILL.md`。

用途：从官方精选目录或 GitHub 仓库安装 Skill。

安全要求：

- 优先官方 curated；
- 安装前阅读 `SKILL.md`、脚本和依赖；
- 检查是否读取密钥、外发数据或执行远程脚本；
- 固定 commit 或版本，避免直接跟随时变分支。

### `careful`、`guard`、`freeze`（A）

来源：gstack，`D:\project\github\gstack\careful\SKILL.md`、`guard\SKILL.md`、`freeze\SKILL.md`。

用途：

- `careful`：在破坏性命令前告警；
- `guard`：危险命令告警并限制编辑目录；
- `freeze`：把当前会话的文件修改限制在指定目录。

注意：这些 Skill 依赖 Claude Code 风格的 hooks 和 shell 脚本。迁移到 Codex 时，应把规则改写为 Codex 可执行的前置检查，或让 Agent 在命令执行前显式自检；不能假定复制目录后 hooks 自动生效。

### `context-save` / `context-restore`（A）

来源：gstack，`D:\project\github\gstack\context-save\SKILL.md`、`context-restore\SKILL.md`。

用途：记录目标、决策、失败尝试、待办和关键文件位置；恢复时先读上下文再继续，避免重复走弯路。

适合跨天任务、长链路重构和多人交接。保存前应脱敏，并避免把密钥写入仓库。

### `docker-management`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\devops\docker-management\SKILL.md`，MIT。

用途：管理容器、镜像、卷、网络、Compose 栈，进行生命周期操作、调试、清理和 Dockerfile 优化。

适合容器化本地开发、部署排障和镜像治理。

风险：

- `docker system prune`、卷删除和强制移除容器可能造成不可逆数据丢失；
- 生产环境必须使用只读或受控凭据；
- 清理命令应先列出目标并二次确认。

### `codex`（A，作为第二意见）

来源：gstack，`D:\project\github\gstack\codex\SKILL.md`。

用途：调用 OpenAI Codex CLI 作为外部审查者或“第二意见”，挑战现有方案。

注意：如果当前已经在 Codex 中工作，此 Skill 的独立价值主要是“换一个上下文重新审查”，而不是再次调用同类模型。它需要安装 Codex CLI 并产生额外调用成本。

### `fastmcp`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\mcp\fastmcp\SKILL.md`，MIT。

用途：用 Python 构建、测试、检查和部署 MCP Server，把 API、数据库或内部工具暴露为 MCP 工具、资源和提示。

适合需要让 Agent 安全访问内部能力的平台。必须先设计认证、授权、速率限制、审计和错误边界，不能直接把生产数据库暴露成无边界的工具。

### `page-agent`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\web-development\page-agent\SKILL.md`，MIT。

用途：把页面内自然语言 GUI Agent 嵌入 SaaS、后台或 B2B 产品，让终端用户通过自然语言操作界面。

适合产品差异化功能，不是服务端浏览器自动化工具。需要评估提示注入、越权操作、可访问性和模型成本。

### `mcporter`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\mcp\mcporter\SKILL.md`，MIT。

用途：通过 CLI 管理、认证、调用 MCP 服务，并生成类型。适合多 MCP 服务联调和开发期排障。

## 开发阶段推荐顺序

1. 读取规格、架构和测试计划；
2. 开启 `freeze` 或明确编辑边界；
3. 小步实现，持续运行最相关的测试；
4. 运行 `review-agent` 做只读缺陷审查；
5. 修复后运行 `qa-only` 做真实路径验证；
6. 提交前再运行一次完整测试；
7. 需要沉淀流程时用 `skill-creator` 写项目 Skill。

## 内容与资产生成

开发阶段的“生成”包括代码之外的文档、图片、音频、视频和测试数据。对应 Skill 在 [07-ai-media-and-integrations.md](07-ai-media-and-integrations.md) 中统一说明。默认原则：

- 先生成草稿，再人工审阅；
- 保留提示词、模型、参数和生成时间；
- 不将客户隐私、未公开素材或密钥发送给第三方；
- 对生成内容做版权、事实、品牌和安全审查；
- 明确哪些资产可重建、哪些必须纳入版本控制。

## 开发质量门禁

- 代码符合现有目录结构、命名和错误处理风格；
- 新逻辑有单元测试，关键路径有集成或浏览器测试；
- 不引入无必要的依赖和抽象；
- 配置有默认值与失败策略；
- 日志不包含密钥、令牌和个人敏感信息；
- 数据库变更可回滚或有恢复方案；
- 公共接口有向后兼容说明；
- diff 中没有生成物、调试代码和无关格式化。

## 常见误区

- 让 Agent 一次改太多文件，导致无法审查；
- 用自动修复 Skill 直接改生产代码，没有先只读报告；
- 安装来源不明的 Skill 并授予完整 shell/网络权限；
- 把“测试通过”理解为“用户路径可用”；
- 生成资产不留提示词和来源，后续无法复现或替换。

