from app.schemas import ShotAnalysis
from app.services.mock import mock_analysis


def test_mock_is_deterministic():
    assert mock_analysis(1, 0.0, 3.0) == mock_analysis(1, 0.0, 3.0)


def test_mock_returns_valid_analysis():
    result = mock_analysis(3, 6.0, 9.0, "测试台词")
    assert isinstance(result, ShotAnalysis)
    assert 0.0 <= result.confidence <= 1.0
    assert result.origin in {"filmed", "ai_generated", "code_generated"}
    assert result.prompt
    assert result.evidence