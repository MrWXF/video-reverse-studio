# video-reverse-studio

视频逆向与提示词生成工作台。后端使用 FastAPI，经典工作区仍由 `/` 提供；React + Vite + TypeScript 新工作区正在渐进迁移，当前入口为 `/app`。

## 当前状态

- `/`：经典 Jinja 工作区，保持可用；
- `/app/reverse`：React 逆向工作区，包含上传、项目详情、SSE 进度和时间轴结构编辑；
- `/app/quality`：React 质量仪表盘；
- `/app/generate`：提示词生成迁移占位页，下一阶段接管。

## 本地运行

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/app` 查看 React 工作区。修改前端后构建到 FastAPI 静态目录：

```powershell
cd web
npm install
npm run build
```

React 开发模式可使用 `npm run dev`，Vite 会把 `/api`、`/static` 和 `/docs` 代理到 `127.0.0.1:8000`。

## 验证

```powershell
python -m pytest -q
python -m ruff check app tests
cd web
npm run typecheck
npm run build
```

架构与迁移说明见 `docs/10-react-frontend-architecture.md`。
