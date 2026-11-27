# video-reverse-studio

视频逆向与提示词生成工作台。后端使用 FastAPI，经典工作区仍由 `/` 提供；React + Vite + TypeScript 新工作区正在渐进迁移，当前入口为 `/app`。

## 当前状态

- `/`：经典 Jinja 工作区，保持可用；
- `/app/reverse`：React 逆向工作区，包含上传、项目详情、SSE 进度和时间轴结构编辑；
- `/app/quality`：React 质量仪表盘；
- `/app/generate`：提示词生成与视频任务工作区，支持 Brief、参考项目、镜头提示词、导出和生成任务。

## 认证与任务

- 默认 fail-closed：未配置 `APP_PASSWORD` 且未显式设置 `ALLOW_INSECURE_NO_AUTH=true` 时，业务接口返回 503。
- Basic Auth 失败按客户端 IP 在 `AUTH_FAILURE_WINDOW_S` 窗口内限流，超过 `AUTH_MAX_FAILURES` 返回 429。
- `/healthz`、`/static/` 和带 token 的 `/share/`、`/api/shares/` 保持公开。
- 上传与评论请求有独立请求体上限；后台任务持久化到 `task_runs`，支持原子领取、租约和重启恢复。
- Mock/降级状态会写入任务 metrics，并在 `/healthz` 和前端界面明确展示。
- `/healthz` 同时检查数据库连通性、ffmpeg/ffprobe、按工作负载拆分的活跃任务数和队列深度。

## 配置

从示例开始，按部署环境修改：

```powershell
Copy-Item .env.example .env
```

- `APP_PASSWORD`：生产环境必须设置；`APP_USERNAME` 默认 `admin`。
- `DATABASE_URL`：留空使用 `DATA_DIR/app.db`；也支持 PostgreSQL URL。
- `MAX_UPLOAD_MB` / `MAX_REQUEST_MB` / `MAX_COMMENT_BODY_KB`：上传、普通 JSON 与公开评论的请求体上限。
- `MAX_ACTIVE_JOBS` / `MAX_ACTIVE_GENERATION_JOBS`：分析与视频生成分别限流，不再互相挤占。
- `TASK_LEASE_S` / `TASK_MAX_ATTEMPTS`：持久任务租约与重试预算，长任务会自动续租。
- `SSE_HEARTBEAT_S` / `SSE_MAX_CONNECTIONS` / `SHARE_COMMENT_LIMIT`：实时连接与公开评论防刷参数。

完整配置项见 `.env.example` 与 `app/config.py`。

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
python -m compileall -q app tests
cd web
npm run typecheck
npm run build
```

当前基线：`140 passed`，Ruff、compileall、TypeScript 和 Vite build 通过。架构与迁移说明见 `docs/10-react-frontend-architecture.md`，问题审计与修复记录见 `docs/09-codebase-audit.md`。
