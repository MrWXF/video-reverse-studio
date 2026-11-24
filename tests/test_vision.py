from types import SimpleNamespace

from app.config import Settings
from app.schemas import ShotAnalysis
from app.services.llm import LLMGateway
from app.services.media import VideoMeta
from app.services.vision import analyze_shot


class _StructuredLLM:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def with_structured_output(self, *_args, **_kwargs):
        return self

    def invoke(self, _messages):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result

    def __or__(self, _other):
        return self


def _gateway(settings, llm):
    gateway = LLMGateway(settings)
    gateway.chat_model = lambda vision=False: llm
    return gateway


def test_vision_uses_mock_when_provider_is_disabled(tmp_path):
    keyframe = tmp_path / "shot.jpg"
    keyframe.write_bytes(b"jpeg")
    settings = Settings(llm_provider="mock", llm_api_key="")

    result = analyze_shot(
        LLMGateway(settings),
        keyframe,
        1,
        0.0,
        2.0,
        "产品旁白",
        VideoMeta(duration=2.0, width=640, height=360, fps=24.0),
    )

    assert isinstance(result, ShotAnalysis)
    assert "已纳入台词特征" in " ".join(result.evidence)


def test_vision_parses_structured_model_output(tmp_path):
    keyframe = tmp_path / "shot.jpg"
    keyframe.write_bytes(b"jpeg")
    parsed = ShotAnalysis(
        shot_type="近景",
        camera_movement="缓慢推镜",
        subject="咖啡杯",
        scene="厨房",
        visual_style="广告质感",
        origin="filmed",
        confidence=0.92,
        prompt="close-up coffee cup",
    )
    raw = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 5})
    llm = _StructuredLLM(result={"raw": raw, "parsed": parsed})
    settings = Settings(
        llm_provider="openai",
        llm_api_key="test-key",
        retry_max_attempts=1,
    )
    gateway = _gateway(settings, llm)

    result = analyze_shot(
        gateway,
        keyframe,
        1,
        0.0,
        2.0,
        "",
        VideoMeta(duration=2.0, width=640, height=360, fps=24.0),
    )

    assert result.subject == "咖啡杯"
    assert gateway.stats() == {
        "calls": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }


def test_vision_falls_back_and_redacts_provider_error(tmp_path):
    keyframe = tmp_path / "shot.jpg"
    keyframe.write_bytes(b"jpeg")
    llm = _StructuredLLM(error=TimeoutError(f"secret path {tmp_path}/x sk-abcdefghijkl"))
    settings = Settings(
        llm_provider="openai",
        llm_api_key="test-key",
        retry_max_attempts=1,
        data_dir=tmp_path,
    )

    result = analyze_shot(
        _gateway(settings, llm),
        keyframe,
        1,
        0.0,
        2.0,
        "",
        VideoMeta(duration=2.0, width=640, height=360, fps=24.0),
    )

    assert result.evidence
    assert "已降级" in result.evidence[-1]
    assert str(tmp_path) not in result.evidence[-1]
    assert "sk-abcdefghijkl" not in result.evidence[-1]
