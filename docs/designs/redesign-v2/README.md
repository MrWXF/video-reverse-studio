# ReelReverse 前端重设计 · Simple Studio

日期：2026-11-27  
状态：待确认设计方向，未修改生产前端代码。

## 先看这里

- 设计评审板：`index.html`
- 工作台首页：`home.html`
- 项目工作台：`workspace.html`
- 提示词工作室：`prompt-studio.html`
- 移动端首页：`mobile.html`
- 预览截图：`previews/`

可以直接双击 HTML 打开，也可以在本目录启动静态预览：

```powershell
python -m http.server 8091 --directory docs/designs/redesign-v2
```

然后打开 `http://127.0.0.1:8091/`。

## 重设计目标

1. 首屏只保留一个主行动：上传参考视频并开始分析。
2. 主流程收敛为三步：上传 → AI 拆解 → 生成提示词。
3. 项目详情先给结论，再按需展示镜头、原始数据和其他细节。
4. 去掉大面积紫色渐变、重复统计卡和过密的信息块，改用暖白画布、墨黑文字和单一珊瑚橙主操作色。
5. 桌面端使用顶部导航，移动端使用底部四入口，减少侧栏与弹窗切换。

## 页面说明

### 工作台首页

- 上传区占据主卡片全宽，是唯一主视觉操作。
- 最近项目和“继续上次”放在右侧，不抢夺首屏焦点。
- 统计信息压缩成两个轻量数字，不再用四张 KPI 卡片占满一屏。

### 项目工作台

- 视频、镜头缩略图、镜头详情同屏。
- AI 摘要使用“为什么有效”的解释性表达，而不是继续堆 Token 和原始字段。
- 完整镜头索引收在右栏，点击即可切换，避免一次平铺 24 张卡片。
- “生成提示词”作为项目页唯一高优先级下一步。

### 提示词工作室

- 用三步进度明确当前阶段。
- 创意描述、模板、镜头数、时长和比例集中在一张表内。
- 右侧固定展示方案摘要和生成按钮，生成前可完整确认。
- 生成结果先给出可扫描的镜头列表，再进入单镜头复制与编辑。

## 视觉系统

| Token | Value |
| --- | --- |
| Canvas | `#F2EEE6` |
| Surface | `#FFFDF8` |
| Ink | `#1B1A16` |
| Accent | `#FF5A36` |
| Success | `#31875D` |
| Border | `#DDD7CA` |
| Radius | `18–22px` |
| Motion | `160–200ms` |

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

- Codex Shell 与仓库文件读取：审查现有 React 页面、样式和路由。
- 本地 FastAPI 服务：读取真实项目数据与当前页面状态。
- Chromium Headless Shell：截取当前页面并验证设计稿渲染。
- HTML / CSS：实现可离线打开的高保真设计稿。

## 实现阶段建议

1. 先重构 `AppLayout`：从左侧栏改为顶部导航 + 移动底部导航。
2. 重写首页信息层级：上传主卡片 + 最近项目侧栏。
3. 将项目详情拆成“概览 / 镜头 / 提示词 / 质量”四个标签，默认镜头视图。
4. 重做提示词表单为三步流程，并修复当前 `/app/generate` 在浏览器中出现的空屏报错。
5. 用同一套设计 token 替换现有 `studio-*.css`，最后补桌面与移动端截图回归。

## 已知现状

截图过程中发现当前 `/app/generate` 页面在浏览器控制台报 `Cannot read properties of undefined (reading 'map')`，页面为空。该问题应在生产前端落地时一并修复。
