# ReelReverse 设计改进提案

> 版本：v0.2 设计稿  
> 更新日期：2026-11-24

## 1. 概述

本文档基于 v0.1 版本的架构分析和问题诊断，提出下一阶段的产品设计改进方向。目标是将 ReelReverse 从「视频分析工具」升级为「视频创作工作流平台」。

### 1.1 设计愿景

```
当前：视频上传 → 分析 → 配方输出

目标：视频上传 → 分析 → 配方输出 → 执行生成 → 效果对比 → 知识沉淀
                        ↓
                    素材库/模板库
```

### 1.2 改进方向

| 方向 | 目标 | 优先级 |
|------|------|--------|
| 产品功能增强 | 提升输出价值，增加用户粘性 | P0 |
| 技术架构改进 | 支持更大规模、更高可靠性 | P1 |
| 用户体验优化 | 降低使用门槛，提高效率 | P1 |
| 商业化准备 | 支持团队协作和付费功能 | P2 |

---

## 2. 产品设计增强

### 2.1 镜头向量检索系统 🔥 推荐

#### 2.1.1 功能描述

将每个分析过的镜头转化为可检索的向量，支持语义相似度检索和特征匹配。

#### 2.1.2 技术方案

```
关键帧图片 → CLIP/SigLIP 编码 → 512维向量 → 向量数据库
```

**技术选型**：
| 组件 | 推荐方案 | 备选方案 |
|------|----------|----------|
| 视觉编码器 | OpenAI CLIP ViT-B/32 | SigLIP, DINOv2 |
| 向量数据库 | Qdrant (自托管) | Milvus, Pinecone |
| 相似度度量 | Cosine Similarity | Euclidean Distance |

**数据模型扩展**：

```python
# app/models.py
class ShotEmbedding(Base):
    __tablename__ = "shot_embeddings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(50))  # "clip-vit-b32"
    vector: Mapped[list[float]] = mapped_column(ARRAY(Float, dimensions=1))  # 512维
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### 2.1.3 API 设计

```python
# 新增 API 端点
@router.get("/api/shots/similar")
def find_similar_shots(
    query: str,              # 文本查询："日落海滩"
    limit: int = 10,
    filters: dict = None,    # 过滤条件：景别、来源等
) -> list[dict]:
    """
    根据文本描述查找相似镜头。
    1. 将查询文本编码为向量
    2. 在向量数据库中搜索最相似的镜头
    3. 返回镜头详情和所属项目信息
    """
    pass

@router.post("/api/shots/{shot_id}/similar")
def find_similar_to_shot(
    shot_id: int,
    limit: int = 10,
) -> list[dict]:
    """
    查找与指定镜头相似的其他镜头。
    用于"找类似运镜"、"找同类主体"场景。
    """
    pass
```

#### 2.1.4 使用场景

1. **灵感发现**：输入"城市夜景"，找到项目中所有夜景镜头
2. **风格复用**：找到与某个镜头风格相似的其他镜头
3. **素材去重**：发现项目中是否有重复或高度相似的镜头

#### 2.1.5 实施计划

| 阶段 | 任务 | 工时 |
|------|------|------|
| Phase 1 | 集成 CLIP 编码器，生成向量 | 2天 |
| Phase 2 | 部署 Qdrant，实现存储和检索 | 2天 |
| Phase 3 | API 开发和前端集成 | 2天 |
| Phase 4 | 性能优化和测试 | 1天 |

**总计**：约 7 人天

---

### 2.2 时间轴交互式编辑器

#### 2.2.1 功能描述

在 Web 界面提供可视化时间轴，让用户可以：
- 直观查看镜头分布和时长
- 调整镜头边界（合并/拆分）
- 实时编辑镜头属性
- 预览修改后的配方效果

#### 2.2.2 UI 设计

```
┌─────────────────────────────────────────────────────────────────┐
│  视频预览                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      [播放窗口]                          │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  时间轴                                                          │
│  ├───Shot 1───┼──Shot 2──┼────Shot 3────┼──Shot 4──┼──...      │
│  0s          2.5s       4.8s           8.2s       12s          │
│  [可拖拽边界]                                                    │
├─────────────────────────────────────────────────────────────────┤
│  当前镜头属性                                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 景别: [中景 ▼]   运镜: [推镜 ▼]   来源: [实拍 ▼]         │  │
│  │ 主体: [可编辑文本框]                                      │  │
│  │ 提示词: [可编辑文本框]                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│  [保存修改] [重新分析当前镜头] [拆分镜头]                        │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.2.3 技术实现

**前端组件**：
```javascript
// app/static/timeline.js
class TimelineEditor {
    constructor(container, shots, duration) {
        this.shots = shots;
        this.duration = duration;
        this.render();
    }
    
    render() {
        // 渲染时间轴
        // 绑定拖拽事件
        // 绑定点击事件
    }
    
    onShotBoundaryDrag(shotIndex, newBoundary) {
        // 更新镜头边界
        // 重新计算时长
        // 触发 onShotChange 回调
    }
    
    onShotClick(shotIndex) {
        // 加载镜头属性到编辑面板
        // 更新视频预览位置
    }
}
```

**后端 API**：
```python
@router.patch("/api/projects/{project_id}/shots/{shot_id}/boundary")
def update_shot_boundary(
    project_id: str,
    shot_id: int,
    start_s: float,
    end_s: float,
    db: Session = Depends(get_db),
) -> dict:
    """
    更新镜头边界，重新抽取关键帧。
    """
    pass

@router.post("/api/projects/{project_id}/shots/{shot_id}/split")
def split_shot(
    project_id: str,
    shot_id: int,
    split_at: float,  # 分割点时间
    db: Session = Depends(get_db),
) -> dict:
    """
    在指定位置拆分镜头，生成两个新镜头。
    """
    pass
```

#### 2.2.4 实施计划

**总计**：约 10 人天

---

### 2.3 AI 视频真伪检测报告

#### 2.3.1 功能描述

深化现有的来源判定功能，输出结构化的「AI 生成概率报告」，用于：
- 媒体审核
- 版权纠纷
- 学术研究
- 合规审查

#### 2.3.2 检测维度扩展

| 维度 | 实拍特征 | AI 生成特征 | 检测方法 |
|------|----------|-------------|----------|
| 皮肤纹理 | 自然毛孔、细纹 | 过度平滑、塑料质感 | 纹理分析 |
| 手指结构 | 正常数量和关节 | 数量异常、变形 | 关键点检测 |
| 瞳孔反射 | 自然的反光 | 不一致或缺失 | 眼部检测 |
| 边缘质量 | 自然过渡 | 模糊或锯齿状 | 边缘检测 |
| 背景一致性 | 物理合理的景深 | 不合理的模糊/重复 | 场景分析 |
| 文字可读性 | 清晰可读 | 乱码或扭曲 | OCR 检测 |
| 光照一致性 | 物理合理的光源方向 | 矛盾的光照 | 阴影分析 |

#### 2.3.3 输出报告格式

```yaml
---
video_id: "abc123"
title: "测试视频.mp4"
overall_verdict: "likely_ai_generated"
overall_confidence: 0.82
generated_at: "2026-11-24T10:00:00Z"
---

# AI 生成概率报告

## 总体判定

- **判定结果**：可能为 AI 生成
- **置信度**：82%
- **主要依据**：皮肤纹理异常、背景重复、手指结构可疑

## 逐项分析

| 维度 | 判定 | 置信度 | 证据 |
|------|------|--------|------|
| 皮肤纹理 | AI 特征 | 85% | 面部区域过度平滑，缺乏自然毛孔 |
| 手指结构 | AI 特征 | 78% | 第 2 镜头左手第 4 指比例异常 |
| 背景一致性 | AI 特征 | 82% | 第 3 镜头背景存在重复纹理块 |
| 光照 | 不确定 | 55% | 光源方向基本一致，无明显矛盾 |
| 文字 | 实拍特征 | 70% | 第 5 镜头背景文字清晰可读 |

## 逐镜详情

### Shot 01 (0.0s - 2.5s)
- 判定：可能 AI 生成（80%）
- 证据：面部皮肤过度平滑，背景建筑边缘有轻微锯齿

### Shot 02 (2.5s - 5.0s)
- 判定：可能 AI 生成（85%）
- 证据：左手第 4 指长度异常，背景存在重复图案

## 建议

- 建议人工复核第 4 镜头，该镜头特征不明显
- 可结合原始视频元数据进一步验证
- 如需法律用途，建议使用专业取证工具
```

#### 2.3.4 API 设计

```python
class DetectionReport(BaseModel):
    video_id: str
    overall_verdict: Literal["likely_filmed", "likely_ai_generated", "uncertain"]
    overall_confidence: float
    dimensions: list[DimensionResult]
    shots: list[ShotDetectionResult]
    recommendations: list[str]

@router.get("/api/projects/{project_id}/ai-detection-report")
def get_detection_report(project_id: str) -> DetectionReport:
    """
    生成 AI 视频真伪检测报告。
    """
    pass

@router.get("/api/projects/{project_id}/ai-detection-report/pdf")
def export_detection_pdf(project_id: str) -> FileResponse:
    """
    导出 PDF 格式的检测报告。
    """
    pass
```

#### 2.3.5 实施计划

**总计**：约 15 人天（含检测模型集成）

---

### 2.4 镜头模板库

#### 2.4.1 功能描述

用户可将优秀镜头保存为「模板」，在后续提示词生成中引用，实现知识沉淀和复用。

#### 2.4.2 数据模型

```python
class ShotTemplate(Base):
    __tablename__ = "shot_templates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)  # 所属用户
    name: Mapped[str] = mapped_column(String(100))  # 模板名称
    description: Mapped[str] = mapped_column(Text)
    
    # 镜头属性
    shot_type: Mapped[str]
    camera_movement: Mapped[str]
    lighting: Mapped[str]
    color_palette: Mapped[list[str]] = mapped_column(JSON)
    visual_style: Mapped[str]
    
    # 提示词模板
    prompt_template: Mapped[str]  # 可包含占位符 {{subject}}
    
    # 分类标签
    tags: Mapped[list[str]] = mapped_column(JSON)
    category: Mapped[str] = mapped_column(String(50))  # 产品/人像/风景
    
    # 来源
    source_project_id: Mapped[str] = mapped_column(String(36), nullable=True)
    source_shot_index: Mapped[int] = mapped_column(Integer, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### 2.4.3 API 设计

```python
@router.post("/api/projects/{project_id}/shots/{shot_index}/save-template")
def save_shot_as_template(
    project_id: str,
    shot_index: int,
    name: str,
    tags: list[str] = [],
    db: Session = Depends(get_db),
) -> dict:
    """将镜头保存为模板"""
    pass

@router.get("/api/shot-templates")
def list_shot_templates(
    category: str = None,
    tags: list[str] = None,
    search: str = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    """搜索模板"""
    pass

@router.post("/api/prompt-projects/{project_id}/apply-template")
def apply_template_to_project(
    project_id: str,
    template_id: int,
    shot_indices: list[int],  # 应用到哪些镜头
    db: Session = Depends(get_db),
) -> dict:
    """将模板应用到指定镜头"""
    pass
```

#### 2.4.4 实施计划

**总计**：约 5 人天

---

### 2.5 配方执行对接 🔥 推荐

#### 2.5.1 功能描述

打通分析到生成的闭环：用户分析视频后，可直接将提示词发送到视频生成平台，一键生成新视频。

#### 2.5.2 支持的平台

| 平台 | API 状态 | 特点 |
|------|----------|------|
| 可灵 (Kling) | 公开 API | 国内领先，支持长视频 |
| 即梦 (Jimeng) | 公开 API | 字节跳动，质量稳定 |
| Runway | 公开 API | 国际领先，Gen-3 模型 |
| Pika | 公开 API | 擅长动画风格 |
| Veo (Google) | 待开放 | 最新 SOTA |

#### 2.5.3 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│                     配方执行引擎                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │  Prompt Plan    │───▶│  格式转换层     │                 │
│  │  (通用格式)     │    │                 │                 │
│  └─────────────────┘    └────────┬────────┘                 │
│                                  │                           │
│          ┌───────────────────────┼───────────────────────┐  │
│          ▼                       ▼                       ▼  │
│  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  │ KlingAdapter│         │RunwayAdapter│         │ PikaAdapter │
│  │   (可灵)    │         │  (Runway)   │         │   (Pika)    │
│  └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
│         │                       │                       │     │
└─────────┼───────────────────────┼───────────────────────┼─────┘
          │                       │                       │
          ▼                       ▼                       ▼
    ┌───────────┐           ┌───────────┐           ┌───────────┐
    │ Kling API │           │Runway API │           │ Pika API  │
    └───────────┘           └───────────┘           └───────────┘
```

#### 2.5.4 数据模型

```python
class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_project_id: Mapped[str] = mapped_column(ForeignKey("prompt_projects.id"))
    
    # 目标平台
    platform: Mapped[str] = mapped_column(String(30))  # kling, runway, pika
    api_config: Mapped[dict] = mapped_column(JSON)  # API Key, Base URL
    
    # 生成参数
    shots_to_generate: Mapped[list[int]] = mapped_column(JSON)  # 镜头索引
    generation_params: Mapped[dict] = mapped_column(JSON)  # 平台特定参数
    
    # 状态
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error: Mapped[str] = mapped_column(Text)
    
    # 结果
    result_videos: Mapped[list[dict]] = mapped_column(JSON)  # [{"shot_index": 1, "url": "..."}]
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### 2.5.5 平台适配器接口

```python
# app/services/generation/adapters/base.py
from abc import ABC, abstractmethod

class GenerationAdapter(ABC):
    """视频生成平台适配器基类"""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str,
        **params
    ) -> str:
        """
        生成视频，返回视频 URL。
        """
        pass
    
    @abstractmethod
    async def status(self, job_id: str) -> dict:
        """
        查询生成任务状态。
        """
        pass
    
    @abstractmethod
    def format_prompt(self, prompt: PromptShot) -> str:
        """
        将通用提示词格式转换为本平台格式。
        """
        pass


# app/services/generation/adapters/kling.py
class KlingAdapter(GenerationAdapter):
    async def generate(self, prompt, duration, aspect_ratio, **params):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.klingai.com/v1/videos/text2video",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "prompt": self.format_prompt(prompt),
                    "duration": int(duration),
                    "aspect_ratio": aspect_ratio,
                    "model": params.get("model", "kling-v1"),
                }
            )
        return response.json()["video_url"]
```

#### 2.5.6 API 设计

```python
@router.post("/api/prompt-projects/{project_id}/generate")
def start_generation(
    project_id: str,
    platform: str,  # kling, runway, pika
    api_key: str,   # 用户提供的 API Key
    shots: list[int] = None,  # 指定镜头，默认全部
    db: Session = Depends(get_db),
) -> dict:
    """
    启动视频生成任务。
    """
    pass

@router.get("/api/prompt-projects/{project_id}/generation-jobs")
def list_generation_jobs(project_id: str, db: Session = Depends(get_db)):
    """列出所有生成任务"""
    pass

@router.get("/api/generation-jobs/{job_id}")
def get_generation_job(job_id: str, db: Session = Depends(get_db)):
    """获取生成任务详情"""
    pass
```

#### 2.5.7 实施计划

| 阶段 | 任务 | 工时 |
|------|------|------|
| Phase 1 | 设计适配器接口和基类 | 1天 |
| Phase 2 | 实现可灵适配器 | 2天 |
| Phase 3 | 实现 Runway 适配器 | 2天 |
| Phase 4 | 任务队列和状态管理 | 2天 |
| Phase 5 | 前端集成和测试 | 2天 |

**总计**：约 9 人天

---

## 3. 技术架构改进

### 3.1 多模态融合分析

#### 3.1.1 当前问题

```
视觉分析 ←── 独立 ──→ ASR 语音识别
     ↓                    ↓
  ShotAnalysis        Transcript
     ↓                    ↓
     └──── 手动拼接 ────┘
```

两者独立处理，缺乏深度融合。

#### 3.1.2 改进方案

```
        ┌─────────────────────────────────────┐
        │          多模态融合引擎             │
        └─────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ 视觉分析 │    │ 音频分析 │    │ 文本分析 │
    │ (画面)   │    │ (情绪)   │    │ (语义)   │
    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │               │               │
         └───────────────┼───────────────┘
                         ▼
                ┌─────────────────┐
                │   融合上下文    │
                │ (RichContext)   │
                └─────────────────┘
```

#### 3.1.3 数据模型扩展

```python
class RichContext(BaseModel):
    """丰富的镜头上下文"""
    
    # 视觉
    visual: ShotAnalysis
    
    # 音频
    audio: AudioAnalysis | None
    transcript: str
    
    # 融合理解
    mood: str  # 欢快/紧张/悲伤/平静
    intensity: float  # 情绪强度 0-1
    narrative_role: str  # 对话/独白/旁白/背景音
    key_entities: list[str]  # 关键实体：人物名、地点等
    
    # 增强的提示词
    enhanced_prompt: str


class AudioAnalysis(BaseModel):
    """音频分析结果"""
    
    mood: Literal["happy", "tense", "sad", "calm", "energetic", "neutral"]
    intensity: float
    has_speech: bool
    has_music: bool
    has_sfx: bool  # 音效
    tempo: str  # fast/medium/slow
    dominant_instruments: list[str]
```

#### 3.1.4 实施计划

**总计**：约 8 人天

---

### 3.2 渐进式增强架构（离线模式）

#### 3.2.1 目标

让用户可以选择：
- **云端模式**：使用 OpenAI 等云端 API
- **本地模式**：使用本地部署的模型

#### 3.2.2 本地模型方案

| 功能 | 云端方案 | 本地方案 |
|------|----------|----------|
| 视觉分析 | GPT-4V | LLaVA-1.6 / Qwen-VL |
| 文本生成 | GPT-4o | Llama 3.1 / Qwen 2.5 |
| 语音识别 | Whisper API | faster-whisper |
| 向量编码 | OpenAI Embedding | CLIP / BGE |

#### 3.2.3 架构设计

```python
# app/config.py
class Settings(BaseSettings):
    # 现有配置...
    
    # 新增：本地模式
    use_local_models: bool = False
    local_llm_model: str = "llava-v1.6-mistral-7b"
    local_text_model: str = "qwen2.5-7b-instruct"
    ollama_base_url: str = "http://localhost:11434"


# app/services/llm.py
class LLMGateway:
    def chat_model(self, vision: bool = False) -> BaseChatModel:
        if self.settings.use_local_models:
            return self._local_model(vision)
        return self._cloud_model(vision)
    
    def _local_model(self, vision: bool) -> BaseChatModel:
        if vision:
            return ChatOllama(
                model=self.settings.local_llm_model,
                base_url=self.settings.ollama_base_url,
            )
        return ChatOllama(
            model=self.settings.local_text_model,
            base_url=self.settings.ollama_base_url,
        )
```

#### 3.2.4 实施计划

**总计**：约 5 人天

---

### 3.3 性能优化：缓存层

#### 3.3.1 缓存策略

| 数据类型 | 缓存策略 | TTL |
|----------|----------|-----|
| 视频元数据 | 内容哈希键 | 永久 |
| LLM 响应 | 输入哈希键 | 24小时 |
| 镜头向量 | 一次性计算 | 永久 |
| 静态资源 | HTTP 缓存 | 7天 |

#### 3.3.2 技术方案

```python
# app/services/cache.py
from functools import wraps
import hashlib
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def cache_llm_response(ttl_seconds=86400):
    """缓存 LLM 响应"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = hashlib.sha256(
                f"{func.__name__}:{str(args)}:{str(kwargs)}".encode()
            ).hexdigest()
            
            # 尝试从缓存获取
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            redis_client.setex(
                key, 
                ttl_seconds, 
                json.dumps(result)
            )
            return result
        return wrapper
    return decorator


@cache_llm_response()
def analyze_shot(gateway, keyframe, ...):
    ...
```

#### 3.3.3 实施计划

**总计**：约 3 人天

---

## 4. 用户体验优化

### 4.1 智能快捷操作

#### 4.1.1 功能列表

| 操作 | 当前流程 | 优化后 |
|------|----------|--------|
| 分析后生成提示词 | 分析 → 返回列表 → 创建提示词项目 | 一键「生成复刻方案」|
| 对比多个版本 | 手动下载对比 | 一键「对比分析」|
| 分享给他人 | 复制 URL | 生成链接 + 二维码 |

#### 4.1.2 UI 设计

```
分析完成页面：
┌─────────────────────────────────────────────────────────────┐
│  ✓ 分析完成                                                 │
│                                                             │
│  [一键生成复刻方案]  [一键分享]  [下载配方]                  │
│                                                             │
│  或继续操作：                                                │
│  - 编辑镜头属性                                              │
│  - 查找相似镜头                                              │
│  - 导出 AI 检测报告                                         │
└─────────────────────────────────────────────────────────────┘
```

#### 4.1.3 实施计划

**总计**：约 3 人天

---

### 4.2 协作工作流 🔥 推荐

#### 4.2.1 功能描述

支持团队协作场景：
- 编导分析视频
- 美术审核镜头
- 执行生成视频
- 客户查看结果

#### 4.2.2 角色与权限

| 角色 | 权限 |
|------|------|
| 所有者 | 全部权限 + 成员管理 |
| 编辑者 | 创建/编辑项目 |
| 审核者 | 查看 + 评论 |
| 查看者 | 仅查看 |

#### 4.2.3 数据模型

```python
class Team(Base):
    __tablename__ = "teams"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    user_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))  # owner/editor/reviewer/viewer
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    team: Mapped["Team"] = relationship(back_populates="members")
```

#### 4.2.4 评论系统扩展

```python
class ShotComment(Base):
    __tablename__ = "shot_comments"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"))
    author_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[str] = mapped_column(Text)
    
    # 支持标记特定区域
    region: Mapped[dict] = mapped_column(JSON, nullable=True)  # {x, y, w, h}
    
    # 状态
    status: Mapped[str] = mapped_column(String(20))  # open/resolved
    resolved_by: Mapped[str] = mapped_column(String(36), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### 4.2.5 实施计划

**总计**：约 12 人天

---

## 5. 数据与监控

### 5.1 分析质量仪表盘

#### 5.1.1 指标设计

| 指标 | 描述 | 用途 |
|------|------|------|
| 来源判定准确率 | 用户修正比例 | 评估模型质量 |
| 字段修正频率 | 各字段被修改的次数 | 发现模型弱点 |
| 平均处理时间 | 视频处理耗时 | 性能监控 |
| Token 消耗 | 每项目的 token 数 | 成本控制 |
| 用户满意度 | 点赞/差评比例 | 产品反馈 |

#### 5.1.2 UI 设计

```
┌─────────────────────────────────────────────────────────────┐
│  质量仪表盘                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ 来源判定准确率   │  │ 字段修正频率     │                │
│  │   87.5% ↑       │  │ 景别: 12%        │                │
│  │   +2.3%         │  │ 运镜: 8%         │                │
│  └──────────────────┘  │ 来源: 15% ←      │                │
│                        └──────────────────┘                │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 修正趋势（过去 30 天）                                │  │
│  │  100% ┤                                              │  │
│  │   90% ┤    ╭───╮     ╭──────╮                       │  │
│  │   80% ┤────╯   ╰─────╯      ╰────────               │  │
│  │        └────────────────────────────────             │  │
│  │          11/1       11/15      11/24                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  💡 建议：来源判定修正率较高，考虑优化证据提取逻辑           │
└─────────────────────────────────────────────────────────────┘
```

#### 5.1.3 实施计划

**总计**：约 5 人天

---

### 5.2 成本监控

#### 5.2.1 功能描述

让用户清晰了解每次分析的成本，并给出优化建议。

#### 5.2.2 成本模型

```python
class CostEstimate(BaseModel):
    """成本预估"""
    
    # 镜头数
    shot_count: int
    
    # Token 预估
    prompt_tokens: int
    completion_tokens: int
    
    # 成本预估
    vision_cost: float  # 视觉分析成本
    text_cost: float    # 文本生成成本
    total_cost: float   # 总成本
    
    # 优化建议
    suggestions: list[str]


@router.post("/api/projects/estimate-cost")
def estimate_cost(
    video_duration: float,
    estimated_shots: int = None,
) -> CostEstimate:
    """
    分析前预估成本。
    """
    pass


@router.get("/api/projects/{project_id}/cost")
def get_project_cost(project_id: str) -> dict:
    """
    分析后实际成本。
    """
    pass
```

#### 5.2.3 优化建议

```
💡 成本优化建议：

1. 当前视频时长 60s，预计生成 18 个镜头。
   调整 max_shots=12 可节省 33% 成本。

2. 关键帧分辨率当前为 768px。
   调整为 512px 对质量影响小，可节省约 15% token。

3. 部分镜头时长 < 1s，建议合并以减少分析次数。
```

#### 5.2.4 实施计划

**总计**：约 3 人天

---

## 6. 实施路线图

### 6.1 Phase 1：核心增强（2-3 周）

| 功能 | 优先级 | 工时 | 价值 |
|------|--------|------|------|
| 镜头向量检索系统 | P0 | 7天 | 高 |
| 配方执行对接（可灵） | P0 | 5天 | 高 |
| 测试覆盖率提升 | P0 | 3天 | 高 |
| 任务重试机制 | P0 | 2天 | 高 |

### 6.2 Phase 2：体验优化（3-4 周）

| 功能 | 优先级 | 工时 | 价值 |
|------|--------|------|------|
| 时间轴编辑器 | P1 | 10天 | 中 |
| 智能快捷操作 | P1 | 3天 | 中 |
| 镜头模板库 | P1 | 5天 | 中 |
| AI 检测报告 | P1 | 10天 | 中 |

### 6.3 Phase 3：协作与商业化（4-6 周）

| 功能 | 优先级 | 工时 | 价值 |
|------|--------|------|------|
| 团队协作功能 | P2 | 12天 | 高 |
| 多模态融合 | P2 | 8天 | 中 |
| 离线模式 | P2 | 5天 | 中 |
| 成本监控 | P2 | 3天 | 中 |

---

## 7. 总结

通过以上设计改进，ReelReverse 将实现以下转变：

| 维度 | 当前状态 | 目标状态 |
|------|----------|----------|
| 定位 | 视频分析工具 | 视频创作工作流平台 |
| 数据 | 单次使用 | 知识沉淀（镜头库、模板库）|
| 闭环 | 仅输出配方 | 分析→生成→对比完整闭环 |
| 用户 | 个人用户 | 支持团队协作 |
| 价值 | 一次性输出 | 持续可复用的知识资产 |

建议优先实施 **镜头向量检索系统** 和 **配方执行对接**，这两个功能能够显著提升产品价值和用户粘性。