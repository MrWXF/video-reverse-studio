# 视频生成闭环（Phase 2 骨架）

## 目标

把“提示词方案”接到可替换的视频生成适配器上，先跑通任务创建、状态轮询、失败重试、结果落盘、预览/下载和取消，再接真实第三方平台。

当前只实现 `mock` 平台，用于验证完整产品流程。真实平台的接口、鉴权、错误码、限流和计费必须以正式文档及测试账号验证后再接入。

## 已实现

- `GenerationJob` 持久化任务表，记录请求参数、进度、错误和逐镜结果。
- 服务端平台配置，前端不接受、不保存、不回传第三方 API Key。
- 逐镜顺序生成，单镜失败不影响后续镜头，整体支持 `succeeded / partial / failed / cancelled`。
- 结果本地落盘到 `data/generations/{prompt_project_id}/{job_id}/`。
- 结果预览与下载接口，路径校验防止目录穿越。
- 可选幂等键，重复提交返回同一任务；幂等键不能跨项目复用。
- 服务重启时，未完成的生成任务会被标记失败，避免永久卡在运行中。
- 提示词工作台支持“生成全部镜头”“生成视频这镜”、任务轮询和取消。

## Mock 行为

`VIDEO_PROVIDER=mock` 时使用本地占位适配器：

- 优先调用 ffmpeg 生成彩色测试视频；媒体类型为 `video/mp4`。
- ffmpeg 不可用时返回可预览的 SVG 占位图；媒体类型为 `image/svg+xml`。
- 结果明确标注“Mock 本地演示”，不代表真实模型效果，也不产生第三方费用。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/generation/capabilities` | 返回当前平台、是否可用和输入约束，不返回密钥 |
| POST | `/api/prompt-projects/{id}/generation-jobs` | 创建生成任务，可指定 `shot_indices` |
| GET | `/api/prompt-projects/{id}/generation-jobs` | 列出项目生成任务 |
| GET | `/api/generation-jobs/{job_id}` | 查询任务和逐镜结果 |
| POST | `/api/generation-jobs/{job_id}/cancel` | 取消排队中或运行中的任务 |
| GET | `/api/generation-jobs/{job_id}/shots/{index}/video` | 预览或下载单镜结果 |

创建任务示例：

```json
{
  "shot_indices": [1, 2],
  "aspect_ratio": "16:9",
  "model": "",
  "idempotency_key": "optional-client-request-id"
}
```

`shot_indices` 为空表示全部镜头。画面比例取请求值，否则继承提示词方案。

## 配置

```dotenv
VIDEO_PROVIDER=mock
VIDEO_MODEL=mock-v1
VIDEO_API_KEY=
VIDEO_BASE_URL=
VIDEO_REQUEST_TIMEOUT_S=180
VIDEO_POLL_INTERVAL_S=2
VIDEO_TIMEOUT_S=600
MAX_ACTIVE_GENERATION_JOBS=2
GENERATION_RETRY_ATTEMPTS=2
```

`VIDEO_API_KEY` 只从服务端环境读取，不写入任务表，不返回 API 响应，也不进入前端页面。

## 真实平台接入清单

1. 完成 Phase 0：验证鉴权、提交、轮询/回调、失败码、限流、结果下载和计费。
2. 在 `app/services/generation_adapters.py` 新增适配器并注册到 `create_adapter`。
3. 适配器返回 `GeneratedVideo`，由统一服务负责落盘、状态和重试。
4. 补充供应商字段映射、超时、取消、幂等和费用计算测试。
5. 多镜头拼接、音频和一致性处理留到单平台闭环验证之后。

## 当前限制

- 仅支持 `mock`；其他平台会明确返回 `503`，不会伪造成功。
- 进程内后台任务适合单实例演示。生产部署需要持久化队列、租约和跨进程取消。
- 生成文件暂不自动清理，需要后续加入保留周期和磁盘配额。
- 未接入真实视频计费，成本面板只覆盖现有 token 用量。
