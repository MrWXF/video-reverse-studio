# 07 AI 媒体与外部集成

目标：为需要图像、音频、视频、搜索、MCP 或页面智能体的产品提供可评估的 Skill 选项，并明确成本、版权和数据风险。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用产品 |
| --- | --- | --- | --- |
| A | `imagegen` | 生成/编辑位图、概念图、海报和 UI 素材 | 设计、营销、内容产品 |
| A | `whisper` | 多语言语音识别、转写和翻译 | 视频、播客、会议、字幕 |
| A | `inference-sh-cli` | 通过 CLI 调用图像、视频、LLM、搜索等模型服务 | 多模型内容生产 |
| A | `duckduckgo-search` | 免费网页、新闻、图片和视频搜索 | 调研、线索发现 |
| B | `stable-diffusion` | 文生图、图生图、修补和自定义扩散管线 | 需要自托管/可控图像生成 |
| B | `fastmcp` | 构建和部署 MCP Server | 内部平台、工具集成 |
| B | `mcporter` | 管理、认证和调用 MCP 服务 | 多 MCP 联调 |
| B | `page-agent` | 在产品页面内嵌入自然语言 GUI Agent | SaaS、后台、B2B |
| B | `parallel-cli` | 网页搜索、抽取、深度研究和监控 | 研究型工作流 |
| B | `qmd` | 本地知识库、文档和会议记录混合检索 | 私有知识库 |
| B | `scrapling` | HTTP 抓取、浏览器自动化和蜘蛛爬取 | 合规的数据采集 |
| B | `concept-diagrams` | 生成教学型 SVG 图解 | 文档、课程、说明页 |

## 逐项说明

### `imagegen`（A）

来源：Codex 内置，`C:\Users\Administrator\.codex\skills\.system\imagegen\SKILL.md`。

适合生成插画、海报、产品概念图、纹理、角色和占位素材，也可编辑现有位图。

使用原则：

- 保留原始提示词、参考图和生成版本；
- 涉及品牌资产时先建立视觉规范；
- 不直接使用生成图冒充真实产品截图；
- 对人物、商标、艺术品风格做版权和肖像权检查；
- 重要资产需人工挑选和后期处理。

不适合替代 SVG 图标系统、代码原生图表或需要像素级品牌规范的 logo。

### `whisper`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\mlops\whisper\SKILL.md`，MIT。

用途：语音转文字、翻译成英文和语言识别，支持多语言和多种模型规模。

适合视频字幕、播客转写、会议记录和语音内容分析。

注意：

- 明确音频数据是否允许上传或本地处理；
- 记录模型规模、语言和准确率；
- 人名、术语和数字需要人工校对；
- 大文件批处理需要控制并发、显存和成本。

### `inference-sh-cli`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\devops\cli\SKILL.md`，MIT。

用途：通过 `infsh` CLI 调用图像生成、视频生成、LLM、搜索、3D 和社交自动化等能力。

适合需要快速比较多个模型的团队。上线前必须确认：

- 当前可用模型和区域；
- 单次调用价格与失败重试成本；
- 输入内容的留存和训练政策；
- 输出内容的商用许可；
- 速率限制、超时和降级模型；
- 供应商锁定和迁移成本。

### `duckduckgo-search`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\research\duckduckgo-search\SKILL.md`，MIT。

用途：无需 API Key 的网页、新闻、图片和视频搜索。

适合调研和公开信息发现。搜索结果必须标注来源和检索时间，不能把搜索摘要当作事实全文。

### `stable-diffusion`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\mlops\stable-diffusion\SKILL.md`，MIT。

用途：用 HuggingFace Diffusers 进行文生图、图生图、修补和自定义扩散管线。

适合需要自托管、风格控制或批量生成的产品。需要 GPU、模型许可审查、显存优化和安全过滤。

### `fastmcp` / `mcporter`（B）

来源见 [03-development-and-generation.md](03-development-and-generation.md)。

适合把内部 API、数据库、搜索或业务动作暴露为 Agent 工具，以及开发和调试 MCP 集成。

最低安全要求：

- 每个工具显式授权；
- 参数白名单和输入校验；
- 速率限制与超时；
- 审计每次调用；
- 对写操作做二次确认；
- 不暴露任意 SQL、任意 shell 或任意 URL 请求。

### `page-agent`（B）

来源见 [03-development-and-generation.md](03-development-and-generation.md)。

适合给现有 Web 产品增加自然语言操作入口。不要把“模型能点击按钮”直接等同于“拥有用户权限”；所有动作仍应经过原系统的鉴权和审计。

### `parallel-cli`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\research\parallel-cli\SKILL.md`，MIT。

用途：Agent 原生网页搜索、抽取、深度研究、数据丰富和监控，优先 JSON 和非交互输出。

适合研究型流程。属于第三方服务，需评估费用、数据留存和结果可追溯性。

### `qmd`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\research\qmd\SKILL.md`，MIT。

用途：用 BM25、向量检索和 LLM 重排搜索本地知识库、笔记、文档和会议记录。

适合私有资料检索。必须配置访问边界，避免把个人或客户资料索引到共享环境。

### `scrapling`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\research\scrapling\SKILL.md`，MIT。

用途：HTTP 抓取、隐匿浏览器、Cloudflare 绕过和蜘蛛爬取。

高风险提示：只抓取你有权访问的数据；遵守 robots、服务条款、版权和隐私法规。不要用绕过机制规避合法的访问控制。

### `concept-diagrams`（B）

来源：hermes-agent，详见 [01-discovery-and-design.md](01-discovery-and-design.md)。适合解释生命周期、流程和概念，不替代专业软件架构图。

## 推荐媒体生产流水线

```text
需求与风格定义
  → imagegen / stable-diffusion（候选视觉）
  → 人工筛选与版权检查
  → inference-sh-cli（需要视频、TTS、模型能力时）
  → whisper（字幕/转写）
  → 人工校对
  → 资产登记：提示词、模型、参数、许可证、版本
  → 发布
```

## 资产登记模板

每个生成资产至少记录：

- 资产 ID 和文件路径；
- 类型、尺寸、时长和格式；
- 生成模型与版本；
- 完整提示词和负面提示词；
- 参考图及其授权来源；
- 生成日期和操作者；
- 商用许可与限制；
- 人工修改记录；
- 可重建步骤；
- 审核结论。

## 成本与可靠性

- 为每类调用设置预算和单次上限；
- 对超时、限流和模型不可用准备降级方案；
- 缓存可复用结果，避免重复生成；
- 记录 token、图片张数、视频秒数和 GPU 时长；
- 批量任务先做小样本，再扩大；
- 重要生成使用可复现的固定参数。

## 数据与合规

- 不上传客户隐私、未公开代码、身份证件和内部密钥；
- 明确供应商是否保留输入、是否用于训练；
- 对生物特征、人脸、声音克隆和未成年人内容做额外审查；
- 检查模型和训练数据许可；
- 对外发布时标注 AI 生成或合成内容（按适用法规）；
- 建立删除和撤回机制。

## 常见误区

- 只看生成效果，不看许可和供应商条款；
- 把 API Key 写进 Skill、脚本或前端；
- 无预算上限地批量调用视频模型；
- 把搜索摘要当作已验证事实；
- 用抓取工具绕过访问控制；
- 生成资产没有提示词和版本，无法复现；
- 让页面 Agent 绕过原有权限系统。

