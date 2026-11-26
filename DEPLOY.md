# ReelReverse — 腾讯云服务器部署文档（Docker）

> 目标服务器：腾讯云 ubuntu@49.234.13.105（4 核 / 4GB / 40GB SSD / 3Mbps）
> 部署方式：Docker 容器 + 宿主机 Nginx 反向代理
> 参照：同机已投产的 ai-weekly-report 发布流程

---

## 0. 架构总览

```
浏览器 ──HTTP:9004──▶ Nginx (宿主机) ──▶ Docker 容器 video-reverse-studio (uvicorn, 127.0.0.1:8900)
                                              │
                                              └──▶ token-plan 网关 (OpenAI 兼容，qwen4-max)
```

- **Docker**：应用及 ffmpeg 打进镜像；数据经 `./data` 卷持久化（SQLite + 上传视频 + 产物）。
- **Nginx 9004**：与 ai-weekly-report（9003）同宿主机 Nginx，处理 512MB 上传与 SSE 透传。
- **端口约定**：80 = enstud-nginx（勿动）；3000 = ai-weekly-report；9003 = ai-weekly-report 入口；**9004 = 本项目入口**。
- 认证：应用层 HTTP Basic（`APP_PASSWORD` 非空即启用，`/healthz` 公开）。

## 1. 首次部署步骤（已执行）

```bash
# 1) 本地打包（排除无关内容）
tar -czf /tmp/vrs.tar.gz --exclude=.git --exclude=.venv --exclude=data \
    --exclude=.idea --exclude=__pycache__ .

# 2) 上传并解压
ssh ubuntu@49.234.13.105 "mkdir -p ~/video-reverse-studio"
scp /tmp/vrs.tar.gz ubuntu@49.234.13.105:~/
ssh ubuntu@49.234.13.105 "tar -xzf ~/vrs.tar.gz -C ~/video-reverse-studio"

# 3) 服务器生成 .env（LLM 配置复用 ~/ai-weekly-report/.env 的网关 + 随机密码）
# 4) docker-compose build && docker-compose up -d
# 5) 配置 /etc/nginx/sites-available/video-reverse-studio（listen 9004 → 127.0.0.1:8900）
# 6) 腾讯云控制台安全组放行 9004 入站
```

## 2. 日常更新发布

```bash
# 本地（Git Bash）
tar -czf /tmp/vrs.tar.gz --exclude=.git --exclude=.venv --exclude=data \
    --exclude=.idea --exclude=__pycache__ .
scp /tmp/vrs.tar.gz ubuntu@49.234.13.105:~/

# 服务器
ssh ubuntu@49.234.13.105
cd ~/video-reverse-studio
tar -xzf ~/vrs.tar.gz -C .
docker-compose build            # 重建镜像
docker rm -f video-reverse-studio   # ⚠️ 必须先删旧容器，见下方注意事项
docker-compose up -d            # 全新创建（data 卷保留，分析结果不丢）
docker image prune -f           # 清理悬空旧镜像
```

## 3. 常用运维命令

| 命令 | 用途 |
|------|------|
| `docker ps` / `docker logs -f video-reverse-studio` | 状态 / 日志 |
| `docker-compose restart` | 重启应用（保留数据） |
| `docker-compose down && docker-compose up -d` | 完整重建容器 |
| `curl 127.0.0.1:8900/healthz` | 容器健康检查（公开，无需认证） |
| `sudo tail -f /var/log/nginx/video-reverse-studio-error.log` | Nginx 错误日志 |
| 备份 | `tar -czf vrs-data-$(date +%F).tar.gz ~/video-reverse-studio/data` |

## 4. 注意事项

- **勿升级/重启宿主机 Docker**：enstud 全栈（nginx/mysql/redis/nacos 等）运行其上；本项目使用现有 docker-compose v1（1.29.2，compose 文件 2.4 语法）。
- **⚠️ compose v1 重建容器的坑（Engine 29 兼容性）**：`docker-compose up -d --force-recreate` 和「镜像变化触发的自动重建」会报 `KeyError: 'ContainerConfig'` 并留下一个 `<hash>_video-reverse-studio` 的改名残留容器。因此**每次更新发布必须**：先 `docker rm -f video-reverse-studio`（如有 `<hash>_` 开头的残留容器也一并删除），再 `docker-compose up -d` 全新创建。全新创建路径不受影响。
- **修改 `.env` 生效方式**：`docker-compose restart` 不会重读 env_file，需按上一条「删容器 + up -d」流程重建。
- **认证开关**：`APP_PASSWORD` 留空 = 关闭登录（当前状态）；设置非空值即启用 HTTP Basic（`/healthz` 始终公开）。
- **内存**：整机 4GB 且与 enstud 共用，容器 `mem_limit: 1g`；上传超大视频时分析进程与 ffmpeg 均在容器内受此约束。
- **带宽 3Mbps**：上传 500MB 视频约需 20+ 分钟，属正常现象；必要时调小 `MAX_UPLOAD_MB`。
- **SSE**：进度推送依赖 Nginx 站点配置中的 `proxy_buffering off`，勿移除。
- **API Key**：仅存服务器 `.env`（不在镜像内，`.dockerignore` 已排除）。
- **HTTPS**：绑域名 + ICP 备案后可用 Certbot。
- **LLM 切换**：改 `~/video-reverse-studio/.env` 的 `LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL` 后重建容器。`LLM_PROVIDER=mock` 即演示模式。
