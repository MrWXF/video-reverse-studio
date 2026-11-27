# ReelReverse 前端重设计 · Simple Studio

日期：2026-11-27  
状态：已确认方向，并已完成生产前端落地。

## 先看这里

- 生产页面：`http://127.0.0.1:8123/app`
- 工作台首页：`http://127.0.0.1:8123/app/reverse`
- 项目工作台：`http://127.0.0.1:8123/app/reverse/<projectId>`
- 提示词工作室：`http://127.0.0.1:8123/app/generate`
- 质量洞察：`http://127.0.0.1:8123/app/quality`
- 设计评审板：`index.html`
- 设计稿：`home.html`、`workspace.html`、`prompt-studio.html`、`mobile.html`
- 设计稿截图：`previews/`
- 生产页面截图：`production-previews/`

## 重设计目标

1. 首屏只保留一个主行动：上传参考视频并开始分析。
2. 主流程收敛为三步：上传 → AI 拆解 → 生成提示词。
3. 项目详情先给结论，再按需展示镜头、原始数据和其他细节。
4. 去掉大面积紫色渐变、重复统计卡和过密的信息块，改用暖白画布、墨黑文字和单一珊瑚橙主操作色。
5. 桌面端使用顶部导航，移动端使用底部四入口，减少侧栏与弹窗切换。

## 生产实现

### 应用外壳

- `web/src/components/AppLayout.tsx`：顶部品牌、工作台/提示词/质量导航、服务状态、新建分析、移动端底部导航。
- 移除了旧的“光晕 / 霓虹”主题切换。
- `web/src/styles/studio-simple.css`：新版设计 token、卡片、按钮、表单、页面布局和移动端适配。

### 工作台首页

- 上传区占据主卡片全宽，是唯一主视觉操作。
- “继续上次”和最近项目放在右侧，不抢夺首屏焦点。
- 保留上传、拖拽、文件大小校验、时长读取、成本预估、项目搜索、状态筛选和刷新。

### 项目工作台

- 视频、镜头缩略图、选中镜头详情同屏。
- 右侧展示 AI 摘要和完整镜头索引，点击缩略图或索引会定位视频。
- 时间轴编辑、边界拖动、键盘微调、拆分、合并、局部重分析、取消、重分析、删除、导出 Markdown/JSON、SSE 刷新全部保留。
- 原始视频、创作底稿和用量改为可展开区域，降低首屏密度。

### 提示词工作室

- 三步进度：创意 Brief → 生成分镜 → 导出方案。
- 表单与右侧方案摘要同屏，生成按钮固定在摘要卡中。
- 生成结果支持逐镜复制、复制全部、导出 Markdown/JSON、重新生成和视频生成记录。
- 已修复旧版 `/app/generate` 因 `job.result` 为空导致的 `Cannot read properties of undefined (reading 'map')` 空屏问题。

### 质量洞察

- 保留原有 KPI、字段修正、趋势、项目明细和建议逻辑。
- 统一套用新版卡片、颜色、字号和响应式布局。

## 视觉系统

| Token | Value |
| --- | --- |
| Canvas | `#F2EEE6` |
| Surface | `#FFFDF8` |
| Ink | `#1B1A16` |
| Accent | `#FF5A36` |
| Accent strong | `#DB3D1C` |
| Success | `#31875D` |
| Border | `#DDD7CA` |
| Radius | `18–22px` |
| Motion | `160–200ms` |

字体使用系统字体，不依赖 Google Fonts 或 CDN。

## 使用的能力与工具

### Skill

- `ui-ux-pro-max`
  - `--design-system`：确定 Minimalism / Swiss Style 方向。
  - `--domain style`：确认适合专业工作台的视觉风格。
  - `--domain product`：参考摄影工作室与创意团队产品模式。
  - `--domain color`：确认中性画布 + 单一 creative accent 的策略。
  - `--domain typography`：参考 editorial + human warmth 的字体组合思路。
  - `--domain ux`：核对渐进披露、视频播放与标题换行规则。
  - `--stack react`：核对受控表单、语义化 HTML、焦点管理和标签关联。

未使用 `hallmark`：其规则要求改造已有设计时必须由用户明确点名。  
未使用 `huashu-design`：其定位是高保真原型/演示物料，且明确不适用于生产级 Web App。

### 工具

- Codex Shell 与仓库文件读取：审查 React 页面、路由、API 和样式。
- 本地 FastAPI 服务：读取真实项目数据并做生产页面验证。
- Chromium Headless Shell：截取桌面端 1440px 和移动端 390px 页面。
- TypeScript / Vite / npm：类型检查与生产构建。
- pytest / ruff：后端测试与静态检查。

## 验证结果

- `npm run typecheck`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：`140 passed`。
- `python -m ruff check app tests`：通过。
- 桌面端回归页面：首页、项目详情、提示词生成、质量洞察。
- 移动端回归页面：首页、项目详情、提示词生成、质量洞察。
- `/app/generate` 已使用真实失败方案、真实完成方案和空状态验证，不再出现空屏。
