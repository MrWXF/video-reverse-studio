# 06 运维、维护与复盘

目标：上线后持续发现异常、定位根因、恢复服务、更新文档，并把经验转成下一次可复用的规则。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用时机 |
| --- | --- | --- | --- |
| S | `investigate` | 系统化根因排查，先调查再修复 | 故障、性能异常、难以复现缺陷 |
| S | `health` | 代码质量与仓库健康度面板 | 周期性维护、版本前盘点 |
| S | `document-generate` | 为功能、模块或整个项目生成缺失文档 | 文档缺口、交接、新人接入 |
| A | `retro` | 工程复盘，整理交付、问题和改进项 | 每周、每版本、事故后 |
| A | `learn` | 管理项目经验，保留决策和踩坑记录 | 持续维护 |
| A | `canary` | 上线后持续观察错误和性能 | 发布观察期 |
| A | `benchmark` | 性能基线和回归对比 | 周期巡检、性能事件 |
| A | `context-save` / `context-restore` | 保存排障上下文，支持交接 | 长故障、跨班次处理 |
| A | `docker-management` | 容器运行、日志、资源与清理 | 容器化运维 |
| A | `1password` | 最小权限读取运维密钥 | 受控排障和发布 |
| B | `oss-forensics` | 供应链与仓库取证 | 安全事件、异常提交、依赖风险 |

## 逐项说明

### `investigate`（S）

来源：gstack，`D:\project\github\gstack\investigate\SKILL.md`。

用途：系统化调试，强调“没有调查就不修复”，追踪数据流、提出假设、验证假设，并在连续失败后停止扩大改动。

适合：

- 线上故障；
- 间歇性缺陷；
- 性能下降；
- 多层系统之间的数据不一致。

建议输入：现象、时间线、影响范围、最近变更、日志、指标、复现步骤和已尝试方案。

注意：调查阶段应先只读；生产日志和数据库查询必须脱敏，并限制为最小必要范围。

### `health`（S）

来源：gstack，`D:\project\github\gstack\health\SKILL.md`。

用途：生成代码质量与仓库健康度面板，帮助发现长期积累的风险。

适合周期维护。它不是安全审计，也不能替代测试覆盖率和生产监控。

### `document-generate`（S）

来源：gstack，`D:\project\github\gstack\document-generate\SKILL.md`。

用途：为功能、模块或整个项目生成缺失文档，包括使用说明、参考和教程。

适合交接、新人接入、API 对外发布和长期无人维护的项目。生成后必须对照代码核实，尤其是命令、参数、权限和示例。

### `retro`（A）

来源：gstack，`D:\project\github\gstack\retro\SKILL.md`。

用途：工程复盘，整理交付内容、问题和改进项。

适合每周或每个版本固定执行。事故复盘应另加时间线、影响、根因、处置和防复发措施。

### `learn`（A）

来源：gstack，`D:\project\github\gstack\learn\SKILL.md`。

用途：管理项目经验，记录已知决策、踩坑和可复用知识。

适合持续维护，但必须避免把一次性猜测写成事实；每条经验应标注来源、适用版本和失效条件。

### `canary`、`benchmark`（A）

来源见 [05-release-and-deployment.md](05-release-and-deployment.md) 和 [04-testing-and-security.md](04-testing-and-security.md)。

发布后观察窗口用 `canary`；周期性能巡检和回归比较用 `benchmark`。两者都需要稳定基线和明确阈值，否则只能得到“看起来快/慢”的主观结论。

### `context-save` / `context-restore`（A）

来源见 [02-architecture-and-planning.md](02-architecture-and-planning.md)。

排障交接时，用它保存：现象、时间线、假设、已排除项、查询语句、日志位置、当前负责人和下一步。不要把生产 secret 或完整客户数据写入上下文。

### `docker-management`（A）

来源与安全要求见 [03-development-and-generation.md](03-development-and-generation.md)。

维护场景建议优先只读检查：

```text
docker ps
docker logs --tail 200 <container>
docker stats --no-stream
docker inspect <container>
docker compose config
```

任何 prune、rm、volume delete 都应先列出目标、确认备份和影响范围。

### `1password`（A）

来源见 [04-testing-and-security.md](04-testing-and-security.md)。运维时应使用最小权限、短期凭据和审计记录。

### `oss-forensics`（B）

来源见 [04-testing-and-security.md](04-testing-and-security.md)。用于安全事件和供应链调查，不是日常维护默认项。

## 维护节奏建议

| 周期 | 动作 | 推荐 Skill |
| --- | --- | --- |
| 每次发布 | 上线观察、错误和性能检查 | `canary` |
| 每周 | 交付复盘、失败方案归档 | `retro`、`learn` |
| 每两周 | 依赖、漏洞、容器镜像和资源检查 | `health`、`docker-management`、`cso`（按需） |
| 每月 | 文档缺口、性能基线、备份恢复演练 | `document-generate`、`benchmark`、自定义运维 Skill |
| 每季度 | 权限、密钥、供应链和灾难恢复审计 | `1password`、`oss-forensics`、`cso` |

## 当前 Skills 覆盖不到、建议自建的维护能力

通用 Skill 无法知道你的系统拓扑、SLO 和值班规则。建议用 `skill-creator` 自建：

1. `incident-response`：故障分级、升级路径、沟通模板、时间线记录；
2. `rollback-runbook`：应用、数据、配置和外部副作用回滚；
3. `slo-review`：SLI/SLO、错误预算、告警阈值和复盘；
4. `dependency-upgrade`：依赖升级、兼容测试和分批发布；
5. `backup-restore`：备份点、恢复演练和 RPO/RTO 验证；
6. `cost-review`：云资源、模型调用和存储成本上限；
7. `support-triage`：用户问题分类、复现、升级和回复模板；
8. `security-incident`：泄露、越权、供应链事件和取证流程。

## 运维指标建议

- 可用性：成功率、错误率、5xx/4xx 分布；
- 延迟：P50/P95/P99、首屏、关键接口耗时；
- 饱和度：CPU、内存、连接池、队列积压；
- 数据：迁移失败、回填进度、数据不一致；
- 成本：请求量、模型 token、存储和带宽；
- 体验：关键路径完成率、前端错误、崩溃率；
- 交付：发布频率、变更失败率、平均恢复时间。

## 常见误区

- 一上来就改代码，不做根因调查；
- 只修表象，不验证同类路径是否也受影响；
- 复盘只写“加强测试”，没有负责人和截止时间；
- 文档生成后不复核，参数和示例已过期；
- 长期不演练备份恢复，真正故障时才发现不可用；
- 运维 Agent 使用长期高权限凭据。

