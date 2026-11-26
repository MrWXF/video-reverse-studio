# 来源、版本与核验

## 核验结论

- 本次在本地文件系统中检索了已克隆的 GitHub 仓库和 Codex 内置 Skills。
- 当前环境对 GitHub 的 HTTPS 访问被网络策略阻断：`Failed to connect to github.com port 443: Bad access`。
- 因此本清单没有提供 star 数、下载量、最新版本排名等无法在线核验的元数据。
- 推荐依据是本地 `SKILL.md` 的 frontmatter、README、许可证和实际文件结构，而不是营销页面。
- 目标写入目录 `D:\project\github\skillsList` 在当前沙箱中不可写；本次产物先生成在项目内 `skillsList` 目录，需在获得目录权限后复制。

## 主要来源

| 来源 | 上游地址 | 本地路径 | 本地快照 | 许可证 | 核验状态 |
| --- | --- | --- | --- | --- | --- |
| Codex 内置 Skills | 随 Codex 安装 | `C:\Users\Administrator\.codex\skills\.system` | 当前安装版本 | 随产品/文件 | 已读取 `SKILL.md` |
| gstack | `https://github.com/garrytan/gstack` | `D:\project\github\gstack` | `a6fb31726cece1d1bba401fde593db7cb96bc738`，2026-05-26 | MIT | 本地读取；未在线复核最新版 |
| hermes-agent optional-skills | `https://github.com/NousResearch/hermes-agent` | `D:\project\github\hermes-agent\optional-skills` | `6fdbf2f2d76cf37393e657bf37ceda3d84589200`，2026-04-23 | 仓库 MIT；推荐项抽查为 MIT | 本地读取；未在线复核最新版 |
| OpenAI Skills 官方精选 | `https://github.com/openai/skills/tree/main/skills/.curated` | 未在本机完整克隆 | 未核验 | 需逐项检查 | 在线连接失败；仅保留官方入口 |

## Codex 内置 Skill 明细

| Skill | 本地路径 | 本次用途 |
| --- | --- | --- |
| `skill-installer` | `C:\Users\Administrator\.codex\skills\.system\skill-installer\SKILL.md` | 从官方精选或 GitHub 安装 Skill |
| `skill-creator` | `C:\Users\Administrator\.codex\skills\.system\skill-creator\SKILL.md` | 创建团队专属 Skill |
| `review-agent` | `C:\Users\Administrator\.codex\skills\.system\review-agent\SKILL.md` | 只读缺陷审查 |
| `imagegen` | `C:\Users\Administrator\.codex\skills\.system\imagegen\SKILL.md` | 位图生成与编辑 |
| `openai-docs` | `C:\Users\Administrator\.codex\skills\.system\openai-docs\SKILL.md` | OpenAI/Codex 文档问答；不属于研发流水线核心 |
| `create-statusline` | `C:\Users\Administrator\.codex\skills\.system\create-statusline\SKILL.md` | 自定义终端状态栏；与本次生命周期推荐无关 |

## gstack 推荐项清单

本清单引用以下本地 Skill：

```text
office-hours
plan-ceo-review
plan-eng-review
plan-design-review
plan-devex-review
design-consultation
design-shotgun
design-html
design-review
devex-review
spec
plan-tune
autoplan
codex
context-save
context-restore
careful
guard
freeze
review
qa
qa-only
browse
cso
benchmark
ship
setup-deploy
land-and-deploy
canary
landing-report
document-release
document-generate
health
investigate
retro
learn
```

路径格式：`D:\project\github\gstack\<skill-name>\SKILL.md`。

## hermes-agent 推荐项清单

| 分类 | Skill | 路径 | 许可证 |
| --- | --- | --- | --- |
| DevOps | `docker-management` | `optional-skills\devops\docker-management\SKILL.md` | MIT |
| AI CLI | `inference-sh-cli` | `optional-skills\devops\cli\SKILL.md` | MIT |
| MCP | `fastmcp` | `optional-skills\mcp\fastmcp\SKILL.md` | MIT |
| MCP | `mcporter` | `optional-skills\mcp\mcporter\SKILL.md` | MIT |
| UX 测试 | `adversarial-ux-test` | `optional-skills\dogfood\adversarial-ux-test\SKILL.md` | MIT |
| 研究 | `duckduckgo-search` | `optional-skills\research\duckduckgo-search\SKILL.md` | MIT |
| 研究 | `parallel-cli` | `optional-skills\research\parallel-cli\SKILL.md` | MIT |
| 研究 | `qmd` | `optional-skills\research\qmd\SKILL.md` | MIT |
| 抓取 | `scrapling` | `optional-skills\research\scrapling\SKILL.md` | MIT |
| 图像 | `stable-diffusion` | `optional-skills\mlops\stable-diffusion\SKILL.md` | MIT |
| 语音 | `whisper` | `optional-skills\mlops\whisper\SKILL.md` | MIT |
| 图解 | `concept-diagrams` | `optional-skills\creative\concept-diagrams\SKILL.md` | MIT |
| Web | `page-agent` | `optional-skills\web-development\page-agent\SKILL.md` | MIT |
| 安全 | `1password` | `optional-skills\security\1password\SKILL.md` | MIT |
| 安全 | `oss-forensics` | `optional-skills\security\oss-forensics\SKILL.md` | 需复核文件内声明 |

## 刻意排除

- **垂直行业 Skill**：区块链、医疗、健身、生物信息、药物发现等。与通用产品生命周期不相关，且合规风险高。
- **通信/邮件/电话 Skill**：只有在产品本身需要短信、电话或 Agent 邮箱时才考虑。
- **`sherlock`**：OSINT 用户名搜索涉及隐私和合规风险，不适合作为通用研发推荐。
- **`conscienceAI` 内的 gstack 副本**：它是应用仓库中的嵌套副本，不是独立上游，且没有清晰的独立许可证入口，因此不单独推荐。
- **`autoplan` / `design-shotgun` 等重型流程**：保留为 B 级按需项，不作为默认安装。

## 本地复核命令

```powershell
# gstack 基本信息
git -C 'D:\project\github\gstack' remote -v
git -C 'D:\project\github\gstack' log -1 --format='%H%n%cd%n%s' --date=iso
Get-Content 'D:\project\github\gstack\LICENSE' -TotalCount 8

# hermes 基本信息
git -C 'D:\project\github\hermes-agent' remote -v
git -C 'D:\project\github\hermes-agent' log -1 --format='%H%n%cd%n%s' --date=iso
Get-Content 'D:\project\github\hermes-agent\LICENSE' -TotalCount 8

# 列出全部 Skill
Get-ChildItem 'D:\project\github\gstack' -Recurse -Filter SKILL.md
Get-ChildItem 'D:\project\github\hermes-agent\optional-skills' -Recurse -Filter SKILL.md

# 读取名称与描述
Get-Content 'D:\project\github\gstack\qa\SKILL.md' -TotalCount 20
```

## 在线复核建议

网络恢复后，建议补充以下信息再决定是否固定安装：

1. 上游最新 commit、release 和最近维护时间；
2. Skill 的许可证与依赖许可证；
3. 是否支持当前 Codex 版本；
4. 是否有未修复的安全问题；
5. 社区使用情况和维护者响应；
6. 安装脚本的网络、文件写入和遥测行为；
7. 是否有官方推荐的签名或校验和。

## 版本策略

- 生产团队应固定 commit，而不是直接跟随默认分支；
- 每次升级前在隔离分支做小范围演练；
- 保留升级前版本和回滚方法；
- 记录升级原因、影响范围和验证结果；
- 对自动更新 Skill 保持谨慎，尤其是拥有 shell、网络和部署权限的 Skill。

