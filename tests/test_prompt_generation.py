from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import PromptBrief, PromptPlan, PromptShot
from app.services.prompt_generation import mock_prompt_plan, normalize_prompt_plan


def make_brief(**overrides) -> PromptBrief:
    values = {
        "title": "清晨咖啡广告",
        "idea": "清晨厨房里的咖啡品牌广告",
        "duration_s": 12.0,
        "shot_count": 4,
    }
    values.update(overrides)
    return PromptBrief(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"idea": "x"},
        {"idea": "  "},
        {"shot_count": 0},
        {"shot_count": 9},
        {"duration_s": 2.9},
        {"duration_s": 120.1},
    ],
)
def test_prompt_brief_rejects_invalid_values(overrides):
    with pytest.raises(ValidationError):
        make_brief(**overrides)


def test_prompt_brief_trims_whitespace():
    brief = make_brief(idea="  咖啡广告  ", title="  方案 A  ")

    assert brief.idea == "咖啡广告"
    assert brief.title == "方案 A"


def test_mock_prompt_plan_is_stable_and_covers_target_duration():
    brief = make_brief()
    first = mock_prompt_plan(brief)
    second = mock_prompt_plan(brief)

    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(
        exclude={"generated_at"}
    )
    assert len(first.shots) == brief.shot_count
    assert [shot.index for shot in first.shots] == [1, 2, 3, 4]
    assert abs(sum(shot.duration for shot in first.shots) - brief.duration_s) < 0.001
    assert all(shot.prompt for shot in first.shots)


def test_normalize_prompt_plan_fixes_timeline_and_prompt_fallbacks():
    brief = make_brief(duration_s=12.0, shot_count=3, negative_prompt="watermark")
    raw = PromptPlan(
        shots=[
            PromptShot(index=3, duration=10.0, subject="coffee cup"),
            PromptShot(index=1, duration=10.0, subject="kitchen"),
            PromptShot(index=2, duration=10.0, subject="steam"),
        ]
    )
    stamp = datetime(2026, 11, 23, tzinfo=timezone.utc)

    plan = normalize_prompt_plan(raw, brief, generated_at=stamp)

    assert [shot.index for shot in plan.shots] == [1, 2, 3]
    assert plan.shots[0].start_s == 0.0
    assert abs(plan.shots[-1].end_s - brief.duration_s) < 0.001
    assert abs(sum(shot.duration for shot in plan.shots) - brief.duration_s) < 0.001
    assert all(shot.prompt for shot in plan.shots)
    assert all(shot.negative_prompt == "watermark" for shot in plan.shots)
    assert all(shot.transition for shot in plan.shots)
    assert plan.generated_at == stamp


def test_normalize_prompt_plan_truncates_excess_shots():
    brief = make_brief(shot_count=2, duration_s=6.0)
    raw = PromptPlan(
        shots=[PromptShot(index=index, duration=2.0) for index in range(1, 5)]
    )

    plan = normalize_prompt_plan(raw, brief)

    assert len(plan.shots) == 2
    assert any("截断" in warning for warning in plan.warnings)


def test_normalize_prompt_plan_requires_shots():
    with pytest.raises(RuntimeError, match="任何镜头"):
        normalize_prompt_plan(PromptPlan(shots=[]), make_brief())
