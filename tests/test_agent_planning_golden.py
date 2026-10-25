"""Deterministic decision-quality gates for the draft agent-native planner."""

from pathlib import Path
from xml.etree import ElementTree

import pytest

from evaluations.planning_golden import (
    GOLDEN_SCENARIOS,
    build_golden_service,
    extract_result_value,
)
from src.schemas import EquipmentPreset, ObservationStyle


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', GOLDEN_SCENARIOS, ids=lambda item: item.scenario_id)
async def test_planning_golden_scenario(scenario):
    result = await build_golden_service(scenario).build_agent_plan(scenario.request)

    assert extract_result_value(result, scenario.expected_path) == scenario.expected_answer
    if result.decision is not None:
        assert result.decision.recommendation_score == result.decision.score_breakdown.final_score
        assert result.decision.reason_summary is not None
        assert result.decision.location.name in result.decision.reason_summary
    if result.alternatives:
        first = result.alternatives[0]
        assert first.score_difference == round(
            result.decision.recommendation_score - first.recommendation_score, 2
        )
        assert set(first.comparison) == {
            'place_contribution',
            'weather_contribution',
            'popularity_adjustment',
            'accessibility_adjustment',
        }
    if result.uncertainties:
        assert result.next_actions


def test_golden_suite_covers_required_styles_presets_and_degradations():
    styles = {scenario.request.observation_style for scenario in GOLDEN_SCENARIOS}
    presets = {
        scenario.request.equipment.preset
        for scenario in GOLDEN_SCENARIOS
        if scenario.request.equipment is not None
    }
    scenario_ids = {scenario.scenario_id for scenario in GOLDEN_SCENARIOS}

    assert len(GOLDEN_SCENARIOS) >= 10
    assert styles >= {
        ObservationStyle.DEEP_SKY,
        ObservationStyle.VISUAL,
        ObservationStyle.PLANETARY,
        ObservationStyle.BEGINNER,
    }
    assert presets >= {
        EquipmentPreset.SEESTAR_S50,
        EquipmentPreset.HOPE_D60_ASI2600MC_AIR,
    }
    assert scenario_ids >= {
        'empty-candidates-action',
        'weather-provider-degradation',
        'night-window-unavailable',
        'historical-multinight',
    }


def test_human_readable_xml_matches_executable_golden_scenarios():
    root = ElementTree.parse(
        Path(__file__).parents[1] / 'evaluations' / 'planning_golden.xml'
    ).getroot()
    xml_pairs = [
        (pair.findtext('question'), pair.findtext('answer')) for pair in root.findall('qa_pair')
    ]
    executable_pairs = [
        (scenario.question, scenario.expected_answer) for scenario in GOLDEN_SCENARIOS
    ]

    assert xml_pairs == executable_pairs
