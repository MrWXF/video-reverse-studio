# 01 需求发现与设计

目标：在写代码前确认“做不做、为谁做、做成什么样”，并把设计决策变成后续可验证的约束。

## 推荐组合

| 等级 | Skill | 主要用途 | 适用时机 |
| --- | --- | --- | --- |
| S | `office-hours` | 用强制问题重新审视产品假设、用户和范围 | 新项目、重大改版、需求争议 |
| S | `plan-design-review` | 按设计维度审查计划，识别 AI Slop 和信息层级问题 | 设计进入开发前 |
| S | `design-review` | 对已实现页面做视觉与交互 QA，并修复问题 | UI 完成、发布前 |
| A | `plan-ceo-review` | 从创始人视角扩大或收缩范围，寻找更高价值切口 | 路线图评审、资源取舍 |
| A | `design-consultation` | 从零建立完整设计系统：审美、字体、颜色、布局、间距、动效 | 0 到 1 产品、品牌升级 |
| A | `design-shotgun` | 一次生成多个设计方向并组织对比选择 | 视觉方向不明确时 |
| A | `design-html` | 把选定设计转成可运行的 HTML/CSS | 设计定稿后、前端开工前 |
| A | `imagegen` | 生成概念图、插画、海报、位图素材 | 缺少视觉资产时 |
| A | `adversarial-ux-test` | 扮演极难取悦的用户，发现真实可用性痛点 | 可用性测试、上线前 |
| B | `concept-diagrams` | 生成教学型 SVG 图解和架构叙事图 | 需要解释复杂概念时 |

## 逐项说明

### `office-hours`（S）

来源：gstack，`D:\project\github\gstack\office-hours\SKILL.md`。

用途：在需求还模糊时，连续追问用户、场景、痛点、替代方案和最小验证方式，产出一份能供后续评审使用的设计文档。

适合：

- 只有一个想法，还没有明确用户和价值主张；
- 需求方已经指定方案，但没人验证问题是否真实；
- 功能越做越多，需要重新收缩范围。

不适合：

- 缺陷修复、文案调整等边界明确的小任务；
- 已经有稳定规格，只需要实现。

验收产物：问题陈述、目标用户、非目标、成功指标、关键假设、备选方案、最小实验。

### `plan-design-review`（S）

来源：gstack，`D:\project\github\gstack\plan-design-review\SKILL.md`。

用途：对设计计划逐维度打分，指出问题并直接改进计划。重点是信息架构、视觉层级、交互状态、可访问性和设计一致性，而不是等代码写完后再补样式。

适合：

- 新页面、新流程和设计系统变更；
- 需要把“好看”拆成可讨论、可验收的标准；
- 产品页面面向客户，需要较高视觉质量。

注意：它评审的是计划和设计约束，不能替代真实浏览器中的 `design-review`。

### `design-review`（S）

来源：gstack，`D:\project\github\gstack\design-review\SKILL.md`。

用途：对已实现界面做设计 QA，检查排版、间距、层级、颜色、交互反馈、AI 生成感和慢交互，并在允许时直接修复。

适合：

- 前端完成后做发布前视觉验收；
- 页面“功能正常但不好看”；
- 需要 before/after 截图和原子提交。

前置条件：本地可启动应用；浏览器工具可用；最好有明确的品牌或设计 token。

### `plan-ceo-review`（A）

来源：gstack，`D:\project\github\gstack\plan-ceo-review\SKILL.md`。

用途：从创始人/业务负责人视角判断是否值得投入，支持扩大范围、选择性扩大、保持范围和缩减范围四种模式。

适合路线图、商业化和资源分配讨论。不要用它替代技术可行性评审。

### `design-consultation`（A，0 到 1 时提升为 S）

来源：gstack，`D:\project\github\gstack\design-consultation\SKILL.md`。

用途：研究同类产品，提出设计方向，形成包含字体、颜色、布局、间距与动效的设计系统，并可生成字体和颜色预览。

适合从零建立品牌或产品视觉规范。已有成熟设计系统时，优先让 Agent 读取现有 token，而不是另起一套。

### `design-shotgun`（A）

来源：gstack，`D:\project\github\gstack\design-shotgun\SKILL.md`。

用途：生成多个设计变体，打开对比板，收集结构化反馈并迭代。

适合视觉方向探索和客户提案。需要人工选择，成本高于单方案生成；不适合每次小改版。

### `design-html`（A）

来源：gstack，`D:\project\github\gstack\design-html\SKILL.md`。

用途：把设计稿转成可运行的 HTML/CSS，并识别 React、Svelte、Vue 等技术栈。

注意：该 Skill 带有 gstack 的 Pretext 布局假设。接入现有前端项目时，应先确认框架、构建工具、组件库和设计 token，不要直接覆盖生产页面。

### `imagegen`（A）

来源：Codex 内置，`C:\Users\Administrator\.codex\skills\.system\imagegen\SKILL.md`。

用途：生成或编辑位图素材，例如海报、插画、纹理、角色、产品概念图和背景。

边界：

- 适合位图，不适合替代 SVG 图标系统或代码原生视觉；
- 生成结果必须做版权、品牌和事实核查；
- 不应把客户隐私图片直接发送到外部生成服务。

### `adversarial-ux-test`（A）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\dogfood\adversarial-ux-test\SKILL.md`，MIT。

用途：扮演抗拒技术、缺乏耐心或容易误操作的用户，实际浏览产品，筛掉噪音后形成可执行缺陷单。

适合发布前的可用性走查，尤其是注册、支付、上传、配置等关键路径。建议配合 `browse` 或真实浏览器执行。

### `concept-diagrams`（B）

来源：hermes-agent，`D:\project\github\hermes-agent\optional-skills\creative\concept-diagrams\SKILL.md`，MIT。

用途：生成扁平、支持明暗主题的 SVG 概念图，适合生命周期、流程、剖面和系统关系说明。

注意：它更偏教学型视觉，不是专业软件架构图工具。软件架构优先使用项目自己的 C4、Mermaid 或架构文档规范。

## 推荐执行顺序

1. `office-hours`：确认问题与范围。
2. `plan-ceo-review`：只在高价值或范围争议时追加。
3. `design-consultation`：需要从零建立视觉规范时执行。
4. `design-shotgun`：需要多个方向时执行，选定一个方向。
5. `plan-design-review`：把选定方向写成可执行设计约束。
6. 开发和生成视觉资产：`design-html` 或现有前端实现，配合 `imagegen`。
7. `design-review`：在真实页面做视觉和交互验收。
8. `adversarial-ux-test`：从困难用户视角走关键路径。

## 设计阶段必须留下的产物

- 一页问题陈述与目标用户；
- 非目标和明确不做的范围；
- 用户主路径与关键异常路径；
- 设计 token：颜色、字体、间距、圆角、阴影、动效；
- 响应式断点和可访问性要求；
- 组件状态：默认、悬停、聚焦、禁用、加载、错误、空状态；
- 视觉验收截图和已知偏差；
- 可量化的成功指标。

## 常见误区

- 把“生成一张好看的图”当成完成设计；
- 只评审桌面端，不检查移动端和键盘操作；
- 让多个设计 Skill 同时给方案，却没有最终决策人；
- 直接复制生成代码到生产项目，不检查现有组件与 token；
- 视觉验收只看截图，不点击真实交互。

