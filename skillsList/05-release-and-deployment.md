# 05 发布与部署

目标：把“代码已完成”变成“可追踪、可验证、可回滚的一次发布”，并确保上线后有人观察、有人处置。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用时机 |
| --- | --- | --- | --- |
| S | `ship` | 发布前检查、版本更新、提交、推送、创建 PR | 准备提交/建 PR 时 |
| S | `setup-deploy` | 探测部署平台、生产 URL 和部署命令 | 首次配置自动部署 |
| S | `land-and-deploy` | 合并 PR、等待 CI、部署并验证生产健康 | 发布上线 |
| S | `canary` | 部署后金丝雀观察：控制台错误、性能、页面失败 | 每次上线后 |
| A | `document-release` | 让 README、使用说明和变更文档与新版本同步 | 发布后 |
| A | `docker-management` | 容器发布、排障和清理 | 容器化部署 |
| A | `1password` | 安全注入部署密钥 | 需要 CI/CD 或云平台凭据 |
| B | `landing-report` | 只读查看发布队列、版本号和开放 PR | 多版本并行发布 |

## 逐项说明

### `ship`（S）

来源：gstack，`D:\project\github\gstack\ship\SKILL.md`。

用途：检测并合并基分支、运行测试、审查 diff、更新 VERSION 与 CHANGELOG、提交、推送并创建 PR。

这是高影响 Skill，可能直接改变 Git 历史并触发 CI。使用前必须确认：

- 当前分支和远端目标；
- 哪些未提交改动会被纳入；
- 是否需要签名、审批或受保护分支流程；
- 版本号规则和 CHANGELOG 约定；
- 是否允许自动 push 和创建 PR；
- 失败时如何停止而不 reset/clean 用户改动。

建议在干净工作树或明确的 feature 分支上使用；不要对包含他人未提交改动的仓库盲目运行。

### `setup-deploy`（S）

来源：gstack，`D:\project\github\gstack\setup-deploy\SKILL.md`。

用途：为 `land-and-deploy` 配置部署设置，包括平台、生产 URL、部署命令和验证方式。

适合首次接入 Vercel、Netlify、Cloudflare、容器平台或自建部署。配置中不得硬编码密钥；应引用 CI secret 或密钥管理服务。

### `land-and-deploy`（S）

来源：gstack，`D:\project\github\gstack\land-and-deploy\SKILL.md`。

用途：合并 PR、等待 CI、执行部署并验证生产健康。它把“已批准”推进到“生产已验证”。

高风险点：

- 自动 merge 可能绕过人工审批；
- 部署命令可能影响生产；
- 健康检查失败时必须停止并回滚，而不是继续重试；
- 生产验证只应使用只读或安全探针，不能提交真实订单。

### `canary`（S）

来源：gstack，`D:\project\github\gstack\canary\SKILL.md`。

用途：部署后监控控制台错误、性能回归和页面失败，形成上线后的第一层观测。

适合每次生产发布。建议预先定义观察窗口、错误率阈值、关键页面和回滚判定条件。它是辅助监控，不替代 APM、日志平台和告警系统。

### `document-release`（A）

来源：gstack，`D:\project\github\gstack\document-release\SKILL.md`。

用途：发布后更新文档，发现过时 README，并梳理参考、操作指南、教程和解释型文档的覆盖情况。

适合对外产品或 API。文档更新应与版本变更同批审查，避免“代码上线、文档过期”。

### `landing-report`（B）

来源：gstack，`D:\project\github\gstack\landing-report\SKILL.md`。

用途：只读发布队列面板，查看版本队列、开放 PR 和下一个版本。只有使用 gstack 的多版本发布流程时才有明显收益。

### `docker-management`（A）

来源与风险见 [03-development-and-generation.md](03-development-and-generation.md)。发布场景重点：

- 构建可复现镜像；
- 固定基础镜像与依赖版本；
- 区分构建时和运行时 secret；
- 部署前检查健康检查、资源限制和持久卷；
- 清理命令必须显式确认目标。

### `1password`（A）

来源与安全要求见 [04-testing-and-security.md](04-testing-and-security.md)。用于 CI/CD、云平台和生产排障时的最小权限密钥注入。

## 推荐发布流程

```text
feature 分支完成
  → review-agent / review
  → 全量测试 + qa-only + design-review
  → cso（敏感变更）
  → ship（检查、版本、提交、PR）
  → 人工审批
  → land-and-deploy（CI、部署、生产健康）
  → canary（观察窗口）
  → document-release（文档同步）
  → 发布记录与复盘
```

## 发布门禁清单

- 目标分支、版本号和发布范围明确；
- 工作树内容均已审查，无意外生成物和密钥；
- 单元、集成、端到端测试通过；
- 关键用户路径已在真实浏览器验证；
- 数据库迁移已验证前进和回滚；
- 新配置有默认值和失败策略；
- 监控、日志、告警已覆盖新增路径；
- 安全和隐私检查完成；
- 回滚命令、负责人和判定阈值明确；
- 发布窗口和业务方已通知；
- 上线后观察期内有人值守。

## 回滚设计

当前推荐的 gstack Skill 更偏“发布”和“部署验证”，回滚仍应作为团队自有 Skill 固化。至少包含：

1. 判定条件：错误率、延迟、关键路径失败、数据异常；
2. 决策人：谁有权回滚；
3. 应用回滚：上一镜像/版本、流量切回、功能开关；
4. 数据回滚：迁移是否可逆、备份点、补偿脚本；
5. 外部副作用：已发送消息、已扣款、已创建资源如何处理；
6. 验证：回滚后健康检查和关键路径验证；
7. 记录：时间线、影响范围、根因和后续行动。

建议用 `skill-creator` 把上述流程写成本项目的 `release-and-rollback` Skill。

## 常见误区

- 自动发布 Skill 在生产仓库拥有不受限权限；
- 没看 diff 就自动提交全部改动；
- 把 CI 通过当作生产可用；
- 上线后不观察，等用户投诉才发现；
- 只准备前进迁移，不准备回滚；
- 发布文档和实际版本脱节；
- 用真实客户账号做生产冒烟测试。

