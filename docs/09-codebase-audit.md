# ReelReverse 代码审计报告

审计日期：2026-11-26

审计范围：`app/templates`、`app/static`、`app/` 后端代码、`tests/`、CI 和现有文档。不包含 `.env`、业务数据和生成产物。

本次只做检查，不修改业务代码。

## 1. 结论先行

当前项目功能状态正常，但仍处在“功能已经很多、工程边界还没有同步升级”的阶段。

- 后端回归：`118 passed`。
- `ruff check app tests`：通过。
- `compileall`：通过。
- 前端 4 个脚本：`node --check` 全部通过。
- OpenAPI：129 个接口全部有 `summary` 和 `operationId`，124 个有 `tags`，但只有 16 个有 `description`。
- 前端没有 `package.json`、锁文件、构建工具或模块系统，采用经典 `<script>` 顺序加载。
- 后端 47 个 Python 文件、7,956 行，276 个函数中 31 个有 docstring（11.2%），63 个类中 10 个有 docstring（15.9%）。

判断：

1. **前端不建议立即全量重写。** 当前原生 JavaScript 可以继续维护，但 `app.js`、`prompt.js`、`style.css` 已进入单体维护风险区。建议先拆模块和补行为测试，再用 Vue 3 + Vite 按工作区逐步迁移。
2. **后端的主要问题不是“没有行内注释”，而是缺少契约说明。** 路由、状态迁移、事务副作用、外部服务重试、错误映射等关键语义没有写清楚，新同学和后续维护者只能通过读完整实现来推断。
3. **工程护栏需要补齐。** 当前后端 CI 较完整，但前端只做了静态字符串断言；浏览器交互、XSS 回归、前端语法检查尚未进入 CI。

## 2. 当前基线

### 2.1 前端规模

| 文件 | 行数 | 大小 | 说明 |
| --- | ---: | ---: | --- |
| `app/static/app.js` | 1,608 | 65.6 KB | 逆向工作区、质量仪表盘、时间轴 |
| `app/static/prompt.js` | 1,814 | 82.3 KB | 提示词生成、版本、分享、交付、生成任务 |
| `app/static/style.css` | 7,804 | 146.4 KB | 全站样式与 A/B 主题 |
| `app/templates/index.html` | 545 | 28.0 KB | 主页面模板 |
| `app/static/shared.js` | 107 | 3.4 KB | 通用工具和全局命名空间 |
| `app/static/share.js` | 123 | 6.0 KB | 分享页 |

页面通过以下顺序加载脚本：

```html
<script src="/static/shared.js"></script>
<script src="/static/app.js"></script>
<script src="/static/prompt.js"></script>
```

没有 `package.json`、依赖锁文件、打包器、模块加载器或组件系统。

### 2.2 后端文档覆盖

| 指标 | 数量 | 比例 |
| --- | ---: | ---: |
| Python 文件 | 47 | - |
| 总行数 | 7,956 | - |
| 函数 | 276 | - |
| 有 docstring 的函数 | 31 | 11.2% |
| 类 | 63 | - |
| 有 docstring 的类 | 10 | 15.9% |
| `#` 行内注释 | 0 | - |

“行内注释为 0”本身不等于代码差。这个项目的命名整体可读，很多代码是直白的 FastAPI/SQLAlchemy 流程。真正缺失的是非直观业务规则和公共契约。

### 2.3 高风险模块

| 文件 | 行数 | 函数数 | 有 docstring 的函数 |
| --- | ---: | ---: | ---: |
| `app/api/prompt_routes.py` | 640 | 29 | 0 |
| `app/api/routes.py` | 597 | 22 | 0 |
| `app/services/prompt_generation.py` | 599 | 17 | 2 |
| `app/services/timeline.py` | 517 | 14 | 1 |
| `app/services/generation.py` | 361 | 11 | 1 |
| `app/services/media.py` | 246 | 11 | 0 |
| `app/schemas.py` | 252 | 0 | 21 个类，0 有类说明 |

## 3. 前端审计

### 3.1 做得好的地方

- 已有统一 DOM 工具、请求封装、转义函数和格式化函数，集中在 `shared.js`。
- 多数动态模板使用了 `esc` 或 `pEsc`，没有发现明显把原始用户输入直接拼进 HTML 的批量模式。
- A/B 两套视觉主题已经存在，设计系统和 CSS 变量已有基础。
- 现有功能覆盖逆向、提示词、质量、版本、分享、交付和视频生成，产品功能密度较高。
- 页面是无构建依赖的静态资源，部署简单，FastAPI 直接托管即可。

### 3.2 主要问题

#### P1：跨文件依赖依赖全局命名空间

- `shared.js` 把工具挂到 `window.ReelReverse`。
- `app.js` 和 `prompt.js` 分别从 `window.ReelReverse` 解构依赖。
- `prompt.js` 直接导出 `window.openPromptFromReference`、`window.openPromptProjectById`、`window.refreshShotTemplates`。
- `app.js` 直接导出 `window.loadQualityDashboard`、`window.openReverseProject`。

这会造成：

- 加载顺序隐式依赖；
- 两个工作区共享状态但没有明确接口；
- 单元测试只能靠启动整页执行；
- 后续迁移框架时难以判断哪些是公共 API、哪些是内部实现。

#### P1：两个主脚本已经过大

`app.js` 1,608 行、`prompt.js` 1,814 行，都同时承担：

- 状态管理；
- 请求和轮询；
- 业务规则；
- HTML 字符串模板；
- 事件绑定；
- 局部 UI 格式化。

这不是“原生 JS 必然差”，而是文件粒度和职责边界已经不适合继续增加功能。下一步新增复杂页面时，冲突和回归成本会明显上升。

#### P1：大量 `innerHTML`

4 个前端脚本中约有 49 处 `innerHTML`。当前有手工转义，但“每个插值点都必须记得转义”无法靠代码结构保证。

建议先补以下 XSS 回归用例，再讨论框架：

- 项目标题包含 `<img src=x onerror=...>`；
- 镜头描述、提示词、审查意见包含 HTML；
- 分享页评论包含脚本标签；
- 模板名称、标签、实体名称包含引号和事件属性；
- 导入或 API 返回的字段包含 HTML。

迁移到 Vue 后默认文本插值会降低这类风险，但不能替代服务端输入约束和回归测试。

#### P2：CSS 单体过大

`style.css` 7,804 行、146 KB。A/B 主题、工作区、弹窗、时间轴、版本对比、分享页都放在一个文件里。

短期可拆为：

- `tokens.css`：变量、颜色、间距、字体；
- `base.css`：reset、布局、通用元素；
- `workspace-reverse.css`；
- `workspace-prompt.css`；
- `timeline.css`；
- `quality.css`；
- `share.css`；
- `themes.css`。

这会显著降低样式冲突，并为后续 Vue 组件迁移提供清晰边界。

#### P1：前端测试验证的是“字符串存在”

`tests/test_frontend.py` 主要断言 HTML/CSS/JS 中存在某些类名、函数名和选择器。这能防止误删钩子，但不能验证：

- 上传后状态是否正确刷新；
- 时间轴拖拽、拆分、合并是否真正可用；
- 提示词生成后编辑是否保存；
- 分享二维码是否打开；
- 浏览器控制台是否报错；
- 小屏和 A/B 主题下是否布局破裂。

现有 Playwright 脚本只在 `data/browser-smoke/` 手工运行，没有进入 CI。

#### P2：没有前端质量工具链

当前只有手工 `node --check`。没有 ESLint、Prettier、TypeScript、组件测试和浏览器测试的自动化入口。

### 3.3 是否需要流行框架

结论：**需要引入，但应按阶段迁移，不能直接全量重写。**

推荐方案：**Vue 3 + Vite**。

原因：

- 现有页面是 HTML 模板加大量 DOM 拼接，Vue 模板语法迁移成本相对低；
- 可以按工作区局部挂载，不需要一次性把 FastAPI 模板改成 SPA；
- 状态、计算属性、组件边界比继续手写 `innerHTML` 清晰；
- 团队若不熟悉 React，Vue 的上手成本更低；
- 后续可以在新模块中逐步启用 TypeScript。

React 也可行，但更适合团队已有 React 经验、需要成熟生态或已有设计系统的情况。当前项目没有证据表明必须选 React。

不建议的做法：

- 不设计组件边界就直接重写；
- 一次性迁移逆向、提示词、质量、分享全部页面；
- 在没有 E2E 基线前替换现有页面；
- 只为“使用框架”而引入复杂状态库或微前端。

### 3.4 前端建议迁移顺序

1. **补护栏**：XSS 回归、浏览器冒烟、前端语法检查进入 CI。
2. **无框架拆模块**：把 API 客户端、格式化、状态、模板渲染和事件绑定分开；消除新增代码对 `window` 的依赖。
3. **拆 CSS**：先做设计令牌和页面级样式文件，不改变视觉。
4. **Vue PoC**：先迁移一个独立区域，例如质量仪表盘或分享页。
5. **逐工作区迁移**：质量 → 逆向 → 提示词。
6. **清理旧代码**：删除全局入口，统一 Vite 构建产物，更新部署说明。

## 4. 后端审计

### 4.1 当前优点

- 路由层、服务层、模型和序列化层已经有基本分层。
- 视频分析、时间轴编辑、提示词生成、视频生成等复杂流程已拆成服务模块。
- 并发容量、重试、脱敏、SSE、上传校验、媒体 Range 等横切能力已有独立实现。
- OpenAPI 的接口摘要和响应码说明覆盖较好。
- 后端测试覆盖面明显好于前端，包含数据库迁移、时间轴、生成、安全、媒体和提示词等。

### 4.2 主要问题

#### P1：核心路由没有函数说明

`app/api/routes.py` 和 `app/api/prompt_routes.py` 共 51 个函数，0 个 docstring。部分接口有 OpenAPI `summary`，但很多复杂行为没有说明，例如：

- 哪些操作会创建后台任务；
- 哪些操作会修改项目状态或使提示词映射失效；
- 哪些错误会映射成 409、422 或 503；
- 删除、取消和重生成是否幂等；
- 是否会写版本快照、审查记录或审计事件。

这类信息应在路由函数 docstring 和 OpenAPI `description` 中同时体现。

#### P1：领域服务缺少状态副作用说明

高风险业务集中在：

- `timeline.py`：时间轴边界调整、拆镜头、合镜头、重新分析、提示词映射失效；
- `prompt_generation.py`：生成重试、规范化、模型失败回退、局部重生成；
- `generation.py`：外部视频模型适配、任务状态、部分成功、取消和下载；
- `quality.py`：质量指标的定义、窗口和聚合口径；
- `media.py`：ffmpeg/ffprobe 的失败模式、超时和输出文件约定。

这些模块最需要说明：

- 输入的不变量；
- 输出和持久化副作用；
- 事务何时提交；
- 失败后系统处于什么状态；
- 哪些步骤可重试、哪些不可重试。

#### P1：Pydantic 数据模型缺少字段语义

`app/schemas.py` 有 21 个类、0 个类 docstring。字段名大多可读，但以下内容仍不明确：

- 哪些字段是用户输入，哪些是服务端派生；
- 时间单位是秒还是毫秒；
- 空值和缺省值的区别；
- 版本兼容约束；
- 哪些字段会进入导出或分享。

建议优先给复杂模型加类 docstring，并在关键字段上使用 `Field(description=...)`。

#### P2：OpenAPI 说明不均衡

129 个接口都有摘要，但只有 16 个有 `description`。建议把下面这些纳入统一规范：

- 创建/取消/重生成类的副作用；
- 202 异步任务的轮询地址；
- 分享权限和过期语义；
- 视频生成部分成功的结果结构；
- 导出 ZIP 的内容清单。

#### P2：README 与架构文档已过期

- `README.md` 只有项目标题，没有安装、启动、配置、测试、目录和部署说明。
- `docs/02-architecture.md` 有一定深度，但没有完整覆盖时间轴编辑、视频生成、质量仪表盘、交付审查、分享和成本统计等新增模块。

## 5. 测试与 CI 审计

### 5.1 已有覆盖

- 118 个 pytest 用例全部通过。
- 后端 lint 和编译检查通过。
- 测试覆盖数据库迁移、安全、上传、时间轴、提示词、生成、质量和分享等主要后端能力。

### 5.2 缺口

- CI 只运行 pytest、ruff、compileall，没有 Node 环境检查。
- 没有浏览器级端到端测试。
- 没有 XSS 回归测试。
- 前端测试是静态文本断言，无法发现运行时异常。
- 没有可访问性、响应式布局或控制台错误检查。

### 5.3 建议补齐的冒烟链路

至少覆盖以下路径：

1. 打开首页，逆向/生成/质量三个工作区可切换。
2. 上传短视频并等待分析完成。
3. 打开项目、播放视频、拖动时间轴、拆分和合并镜头。
4. 从逆向项目打开提示词生成，并检查参考上下文。
5. 生成提示词、编辑镜头、重生成、版本对比和恢复。
6. 创建分享链接，打开分享页并提交评论。
7. 导出 Markdown 和 ZIP。
8. A/B 主题切换，控制台无异常。

## 6. 优先级建议

### 阶段 0：基线护栏（S/M）

- 新增本审计报告。
- 增加前端 XSS 回归用例。
- 将 `node --check`、ESLint 和 Playwright 冒烟纳入 CI。
- 更新 README 的启动、配置和测试说明。

验收：恶意字段无法执行脚本；CI 能发现前端语法和关键交互回归。

### 阶段 1：低风险整理（M）

- 拆分 `shared.js`：API、存储、格式化、DOM、toast 分离。
- 拆分 `app.js` 和 `prompt.js` 的状态、渲染和事件入口。
- 拆分 `style.css`，不改变视觉。
- 给共享接口定义明确的导出对象，不再新增 `window` 全局函数。

验收：页面行为不变；新增功能只需修改对应模块；现有测试继续通过。

### 阶段 2：后端文档化（M）

- 先补 7 个高风险模块的模块级和公共函数 docstring。
- 补复杂路由的副作用、错误码和事务边界。
- 补 Pydantic 模型和关键字段说明。
- 将重要说明同步到 OpenAPI `description`。

验收：新维护者不看完整实现也能理解输入、输出、异常和持久化影响。

### 阶段 3：Vue 3 试点（M/L）

- 引入 Vite、Vue 3 和最小测试工具链。
- 先迁移质量仪表盘或分享页。
- 确定组件、状态、API 客户端和样式规范。
- 验证 FastAPI 托管构建产物的部署方式。

验收：试点页面功能等价、浏览器测试通过、构建产物可部署，旧页面不受影响。

### 阶段 4：逐工作区迁移（L）

- 迁移逆向工作区。
- 迁移提示词工作区。
- 清理旧脚本和全局入口。
- 最后更新架构文档和迁移记录。

验收：不再依赖 `window` 通信，前端有统一构建和质量门禁，核心链路 E2E 全绿。

## 7. 建议的 Backend Docstring 规范

不是给每行代码写注释，而是只写实现本身无法直接表达的内容。

公共函数至少说明：

- 业务目的；
- 参数含义与单位；
- 返回结果；
- 会抛出的业务异常；
- 是否提交事务；
- 是否会创建后台任务或修改项目状态。

建议示例：

```python
def split_timeline_shot(...):
    """Split one shot at a timestamp and queue targeted re-analysis.

    The mutation is persisted immediately. A queued timeline job then
    re-probes the source video, rebuilds affected shots, and invalidates
    linked prompt mappings that reference the old shot structure.

    Raises:
        TimelineConflictError: The project already has an active job.
        TimelineValidationError: The split point is outside the allowed range.
        TimelineCapacityError: The global analysis capacity is exhausted.
    """
```

行内注释只建议保留在以下位置：

- 并发与锁；
- 重试和退避；
- 时间容差和浮点边界；
- 外部服务兼容性；
- 安全校验；
- 有意为之的降级逻辑。

## 8. 最终判断

- **前端框架：需要，但采用渐进式 Vue 3 + Vite，而不是全量重写。**
- **后端备注：需要补，但重点补业务契约和副作用，不追求注释行数。**
- **最优先任务：补 XSS 与浏览器冒烟护栏，再拆前端模块，最后迁移框架。**
- **当前不建议做：无测试基线的大规模前端重写，或给所有函数机械添加无信息量 docstring。**

建议下一步从阶段 0 开始：先建立安全和交互基线，再进入低风险模块化。

## 9. 后端注释补全记录

2026-11-26 已完成第一轮后端注释补全，范围包括：

- 所有非空 Python 模块的模块级 docstring；
- 276/276 个函数和 63/63 个类的 docstring；
- 路由副作用、事务提交、后台任务、容量限制、异常映射和外部服务降级说明；
- ORM 模型、Pydantic 数据契约、序列化输出和核心服务入口说明。

验证结果：

- `python -m pytest -q`：118 passed；
- `python -m ruff check app tests`：通过；
- `python -m compileall -q app tests`：通过。

这里的 100% 指 docstring 存在率，不代表每个函数都写了长篇说明；私有且语义直白的辅助函数保持了一句话说明，复杂业务补了副作用和异常契约。
