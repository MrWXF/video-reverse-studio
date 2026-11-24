import pytest

from app.schemas import ShotAnalysis
from app.services.mock import MockScenarioError, mock_analysis


def test_mock_is_deterministic():
    assert mock_analysis(1, 0.0, 3.0) == mock_analysis(1, 0.0, 3.0)


def test_mock_returns_valid_analysis():
    result = mock_analysis(3, 6.0, 9.0, "测试台词")
    assert isinstance(result, ShotAnalysis)
    assert 0.0 <= result.confidence <= 1.0
    assert result.origin in {"filmed", "ai_generated", "code_generated"}
    assert result.prompt
    assert result.evidence


def test_mock_uses_transcript_and_supports_failure_scenarios():
    first = mock_analysis(1, 0.0, 2.0, "咖啡机开始萃取")
    second = mock_analysis(1, 0.0, 2.0, "人物推门进入")

    assert first.prompt != second.prompt
    assert "咖啡机开始萃取" in first.prompt
    with pytest.raises(MockScenarioError):
        mock_analysis(1, 0.0, 2.0, scenario="fail")
    with pytest.raises(MockScenarioError):
        mock_analysis(2, 0.0, 2.0, scenario="fail_shot", fail_shot=2)
