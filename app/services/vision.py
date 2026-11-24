import base64
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from ..prompts import load_prompt
from ..schemas import ShotAnalysis
from .llm import LLMGateway
from .media import VideoMeta
from .mock import mock_analysis

logger = logging.getLogger(__name__)


def _data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _user_text(
    index: int,
    start_s: float,
    end_s: float,
    transcript: str,
    meta: VideoMeta,
) -> str:
    lines = [
        f"镜头序号：{index}",
        f"时间区间：{start_s:.2f}s - {end_s:.2f}s（时长 {end_s - start_s:.2f}s）",
        f"视频信息：{meta.width}x{meta.height}，{meta.fps:.2f}fps，总时长 {meta.duration:.2f}s",
    ]
    if transcript:
        lines.append(f"该镜头对齐台词：{transcript}")
    lines.append("请分析这张关键帧，并给出可执行的复刻提示词。")
    return "\n".join(lines)


def analyze_shot(
    gateway: LLMGateway,
    keyframe: Path,
    index: int,
    start_s: float,
    end_s: float,
    transcript: str,
    meta: VideoMeta,
) -> ShotAnalysis:
    llm = gateway.chat_model(vision=True)
    if llm is None:
        return mock_analysis(index, start_s, end_s, transcript)

    messages = [
        SystemMessage(content=load_prompt("shot_analysis")),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": _user_text(index, start_s, end_s, transcript, meta),
                },
                {"type": "image_url", "image_url": {"url": _data_url(keyframe)}},
            ]
        ),
    ]

    try:
        structured = llm.with_structured_output(ShotAnalysis, include_raw=True)
        result = structured.invoke(messages)
        raw = result.get("raw") if isinstance(result, dict) else None
        parsed = result.get("parsed") if isinstance(result, dict) else None
        if raw is not None:
            gateway.record_usage(raw)
        if parsed is not None:
            return parsed
        raise ValueError("结构化输出解析失败")
    except Exception as exc:
        logger.warning("structured output failed for shot %s: %s", index, exc)

    try:
        chain = llm | JsonOutputParser()
        data = chain.invoke(messages)
        return ShotAnalysis.model_validate(data)
    except Exception as exc:
        logger.error("vision analysis failed for shot %s: %s", index, exc)
        fallback = mock_analysis(index, start_s, end_s, transcript)
        fallback.evidence.append(f"LLM 调用失败，已降级：{str(exc)[:180]}")
        return fallback