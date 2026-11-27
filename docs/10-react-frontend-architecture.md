# React 前端架构与渐进迁移设计

> 日期：2026-11-26  
> 技术路线：方案 B，React + Vite + TypeScript  
> 当前阶段：阶段 4（提示词工作区）进行中

## 1. 目标

将现有 Jinja 单页、原生 JavaScript 和全局函数式前端逐步迁移为 React 应用，同时满足：

- 保留现有 FastAPI API、Basic Auth 和同源部署方式；
- 保留现有 A/B 视觉主题，不在框架迁移中重做视觉；
- 新代码具备组件边界、明确类型、路由和可测试入口；
- 旧页面在迁移完成前继续可访问，支持对照和回滚；
- 不使用一次性大重写，按工作区逐块切换。

## 2. 当前基线

- `web/` 已提供 React 18.3、Vite 5、TypeScript strict、路由、API 客户端、Zustand 和 Toast；
- `/app/reverse`、`/app/quality` 和 `/app/generate` 已可运行，经典 `app.js`、`prompt.js` 和 `style.css` 仍保留在 `/` 作为对照；
- `web/package.json` 和 `web/package-lock.json` 已提交，CI 使用 `npm ci`、typecheck 和 build；
- 后端已提供项目、提示词、质量、分享和生成任务 API，当前测试基线为 `140 passed`。

这些交互已经达到 SPA 复杂度，继续使用全局 DOM 拼接会增加状态同步和回归风险。

## 3. 技术决策

| 领域 | 选择 | 说明 |
| --- | --- | --- |
| 框架 | React 19 目标，当前离线环境先使用 React 18.3 验证 | 代码只使用 React 18/19 兼容 API；联网后升级依赖 |
| 构建 | Vite 5 | 开发代理 FastAPI，生产输出静态资源 |
| 语言 | TypeScript strict | 先覆盖新代码，不反向污染后端 |
| 路由 | React Router 6 | 逆向、生成、质量和分享独立 URL |
| UI 状态 | Zustand | 主题、Toast 等跨页面轻状态 |
| 服务端状态 | 当前使用小型查询 Hook，联网后切 TanStack Query | 避免离线环境阻塞迁移，接口层保持可替换 |
| 样式 | 现有 CSS 变量 + 组件样式 | 保留 A/B 主题，不立即引入 Tailwind 或重型组件库 |
| 测试 | TypeScript 检查 + Vite build，后续补 Vitest/Playwright | 先保证可构建和浏览器可验证 |

React 版本说明：当前锁定在 React 18.3.1，代码不依赖 React 19 专属 API。依赖可通过 `npm ci` 复现；后续升级 React 19 时同步更新 `react`、`react-dom` 和类型包即可。

## 4. 部署结构

开发环境：

```text
Vite :5173  --/api,/static-->  FastAPI :8000
```

生产环境：

```text
FastAPI /app/*  ->  app/static/react/index.html
FastAPI /static/* ->  app/static/**
FastAPI /api/*  ->  现有接口
```

迁移期间：

- `/` 继续提供旧页面；
- `/app` 提供 React 新页面；
- 功能等价并通过浏览器验证后，再将 `/` 切换为 React 入口；
- 旧 `app.js`、`prompt.js` 在最后一个工作区迁移完成前不删除。

## 5. 目录结构

```text
web/
  src/
    api/            # fetch 客户端、接口类型、端点封装
    components/     # App Shell、Toast、状态和通用展示
    features/
      reverse/      # 逆向工作区
      generate/     # 提示词生成
      quality/      # 质量仪表盘
      share/        # 分享页
    hooks/          # 数据加载、SSE、轮询
    store/          # Zustand UI 状态
    styles/         # 新组件样式；继续复用 /static/style.css
    main.tsx
    App.tsx
```

## 6. 路由设计

| 路由 | 页面 | 迁移顺序 |
| --- | --- | --- |
| `/reverse` | 逆向项目列表与上传 | 第二 |
| `/reverse/:projectId` | 镜头、详情和时间轴 | 第三 |
| `/generate` | 提示词 Brief 与项目列表 | 第四 |
| `/generate/:projectId` | 镜头编辑、版本、分享与导出 | 第五，未完成 |
| `/quality` | 质量仪表盘 | 第一，已完成试点 |
| `/share/:token` | 对外分享页 | 第六，优先保留现有服务端入口 |

## 7. 状态边界

- URL：当前工作区、项目 ID、版本 ID 和筛选条件；
- Zustand：主题、Toast、临时面板状态；
- 查询 Hook：项目列表、项目详情、质量数据、提示词详情；
- 本地组件状态：表单草稿、弹窗、拖拽和时间轴编辑；
- 服务端：任务状态、版本、分享 token 和生成结果。

不把服务端实体复制进 Zustand，避免缓存与后端状态分叉。

## 8. API 边界

- 所有请求通过 `web/src/api/client.ts`；
- `credentials: "same-origin"`，保持 Basic Auth 和同源部署；
- 非 2xx 响应统一提取 `detail`，抛出 `ApiError`；
- 上传使用 `FormData`，不手写 Content-Type；
- SSE 先保留 `EventSource`，轮询作为降级；
- 删除、发布、生成等副作用操作必须由用户显式触发。

## 9. 样式策略

- 继续加载 `/static/style.css`；
- 新组件使用现有 class 命名和 CSS 变量；
- 新布局样式集中在 `web/src/styles/app.css`；
- A/B 主题通过 `html[data-style]` 和 `localStorage` 保持；
- 不在迁移阶段同时替换视觉系统，避免两个变量叠加。

## 10. 迁移阶段

### 阶段 1：基础工程与质量页（已完成）

- 创建 React/Vite/TypeScript 工程；
- 建立 App Shell、路由、API 客户端、Zustand 和 Toast；
- 迁移质量仪表盘；
- 构建产物由 FastAPI `/app` 提供；
- 保留旧页面作为对照。

验收：`/app/quality` 与旧质量页数据一致；TypeScript 和 Vite build 通过；旧页面不受影响。

### 阶段 2：逆向工作区（已完成）

- 项目列表、上传、成本预估；
- 项目详情、视频、镜头卡片；
- SSE 与轮询；
- 删除、取消、重新分析。

### 阶段 3：时间轴（已完成）

- 镜头选择、边界拖动、键盘微调；
- 拆分、合并、局部重分析；
- 与项目详情查询缓存同步。

验收：`/app/reverse/:projectId` 显示时间轴；拖动边界、方向键微调、拆分、合并和局部重分析均调用现有 API；运行中的任务会锁定编辑控件；A/B 主题下样式正常。

### 阶段 4：提示词生成（进行中）

已完成：

- Brief、参考项目、方案查看、重新生成；
- Markdown/JSON 导出；
- 视频生成任务提交与状态查看。

待完成：

- 逐镜编辑、字段锁定和实体一致性编辑；
- 版本对比与恢复；
- 分享、评论和 ZIP 导出；
- 成片回测页面。

验收：`/app/generate` 与经典提示词工作区在主链路上功能等价；逐镜编辑、版本、分享评论和回测均有浏览器回归。

### 阶段 5：切换入口（待阶段 4 完成后）

- 根路径切到 React；
- 更新测试和部署文档；
- 删除旧脚本与重复样式；
- 补 Playwright 端到端回归。

## 11. 风险与约束

- 当前无外网，依赖来自本机已有安装；不能声称完成 React 19 实机验证；
- 现有 CSS 体量大，迁移时必须使用相同 class 和 DOM 语义；
- SSE、拖拽和上传进度需要真实浏览器验证；
- 不能在无测试基线时直接删除旧入口；
- 分享页涉及公开 token 和评论，迁移优先级放在最后。

## 12. 本次完成标准

- `web/` 工程可开发、可类型检查、可构建；
- FastAPI 提供 `/app` 入口；
- React 质量页读取真实 `/api/insights/quality`；
- 再切回旧 `/` 页面仍正常；
- 记录剩余迁移任务、风险与验证基线。

## 13. 当前验证基线

```powershell
cd web
node .\node_modules\typescript\bin\tsc --noEmit
node .\node_modules\vite\bin\vite.js build

cd ..
python -m pytest -q
python -m ruff check app tests
```

当前结果：TypeScript 通过、Vite 构建通过、后端测试 `140 passed`、Ruff 和 compileall 通过。浏览器验证覆盖 `/app/reverse`、项目详情、24 镜头时间轴、A/B 主题、拖动、键盘微调、拆分、合并和局部重分析；Playwright 与真实 XSS 浏览器回归仍待补齐。

## 14. Skills 使用说明

- Codex 运行时加载目录为 `C:\Users\Administrator\.codex\skills\.system`；本会话可用技能为 `imagegen`、`openai-docs`、`skill-creator`、`skill-installer`。
- `D:\project\github\skillsList` 是设计与研发生命周期参考库，当前没有标准 `SKILL.md` 包结构，因此按需直接读取 `design/`、`development/`、`testing/` 等文档，不参与应用运行或构建。
- 当前沙箱对全局 Codex 技能目录只有读权限，未把参考库复制进去；这不影响本项目开发、测试和部署。

