"""Agent-native request and response models for the future unified planner."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.base import GeoBounds, GeoPoint
from src.schemas.places import StargazingLocation
from src.schemas.planning import (
    ObservationStyle,
    ObservationWindow,
    PlanningTarget,
    ScoreBreakdown,
)


class EquipmentPreset(StrEnum):
    """Stable equipment presets accepted by the agent-native planner."""

    SEESTAR_S50 = 'seestar_s50'
    HOPE_D60_ASI2600MC_AIR = 'hope_d60_asi2600mc_air'
    CUSTOM = 'custom'


class AgentLocationIntent(BaseModel):
    """One human place name, center point, or exact bounding box."""

    model_config = ConfigDict(extra='forbid')

    place_name: str | None = Field(
        default=None, description='Human-readable place to resolve, for example 浙江省安吉县'
    )
    center: GeoPoint | None = Field(
        default=None, description='Known center coordinate when geocoding is unnecessary'
    )
    bounds: GeoBounds | None = Field(
        default=None, description='Exact search bounds for advanced callers'
    )
    radius_km: float = Field(
        default=50.0,
        gt=0,
        le=300,
        description='Search radius around a place name or center point',
    )

    @model_validator(mode='after')
    def require_one_location_mode(self) -> AgentLocationIntent:
        modes = (
            bool(self.place_name and self.place_name.strip()),
            self.center is not None,
            self.bounds is not None,
        )
        if sum(modes) != 1:
            raise ValueError('Provide exactly one of place_name, center, or bounds.')
        if self.place_name is not None:
            self.place_name = self.place_name.strip()
        return self


class OpticalOverrides(BaseModel):
    """Optional optics fields that override a preset or define custom equipment."""

    model_config = ConfigDict(extra='forbid')

    focal_length_mm: float | None = Field(default=None, gt=0)
    aperture_mm: float | None = Field(default=None, gt=0)
    sensor_width_mm: float | None = Field(default=None, gt=0)
    sensor_height_mm: float | None = Field(default=None, gt=0)
    sensor_pixel_size_um: float | None = Field(default=None, gt=0)
    central_obstruction_pct: float | None = Field(default=None, ge=0, le=50)
    reducer_factor: float | None = Field(default=None, gt=0)
    barlow_factor: float | None = Field(default=None, gt=0)
    mount_type: str | None = Field(default=None, pattern='^(equatorial|altaz)$')
    filter_type: str | None = Field(default=None, min_length=1, max_length=32)


class AgentEquipmentIntent(BaseModel):
    """Equipment preset plus optional advanced optical overrides."""

    model_config = ConfigDict(extra='forbid')

    preset: EquipmentPreset = Field(description='Stable equipment preset or custom configuration')
    overrides: OpticalOverrides = Field(
        default_factory=OpticalOverrides,
        description='Explicit fields that override the selected preset',
    )

    @model_validator(mode='after')
    def validate_custom_equipment(self) -> AgentEquipmentIntent:
        if self.preset == EquipmentPreset.CUSTOM and self.overrides.focal_length_mm is None:
            raise ValueError('custom equipment requires overrides.focal_length_mm.')
        return self


class ResolvedEquipment(BaseModel):
    """Normalized optical configuration actually used for target matching."""

    preset: EquipmentPreset = Field(description='Preset selected by the caller')
    focal_length_mm: float = Field(gt=0)
    aperture_mm: float | None = Field(default=None, gt=0)
    sensor_width_mm: float | None = Field(default=None, gt=0)
    sensor_height_mm: float | None = Field(default=None, gt=0)
    sensor_pixel_size_um: float | None = Field(default=None, gt=0)
    central_obstruction_pct: float = Field(default=0, ge=0, le=50)
    reducer_factor: float = Field(default=1.0, gt=0)
    barlow_factor: float = Field(default=1.0, gt=0)
    mount_type: str = Field(default='equatorial', pattern='^(equatorial|altaz)$')
    filter_type: str | None = Field(default=None)


class AgentPlanningRequest(BaseModel):
    """User-intent request for the future ``plan_stargazing_session`` entry point."""

    model_config = ConfigDict(extra='forbid')

    location: AgentLocationIntent
    start_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    time_zone: str = Field(default='Asia/Shanghai', min_length=1)
    nights: int = Field(default=3, ge=1, le=7)
    observation_style: ObservationStyle = Field(default=ObservationStyle.BALANCED)
    equipment: AgentEquipmentIntent | None = Field(default=None)
    candidate_limit: int = Field(default=3, ge=1, le=10)
    target_limit: int = Field(default=5, ge=1, le=20)
    avoid_popular_spots: bool = Field(default=False)
    prefer_quiet_at_night: bool = Field(default=False)
    popularity_radius_km: float = Field(default=3.0, gt=0, le=20)


class ResolvedPlanningLocation(BaseModel):
    """Resolved and normalized search geography echoed in the result."""

    input_mode: str = Field(description='place_name, center, or bounds')
    input_text: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    center: GeoPoint
    bounds: GeoBounds
    radius_km: float | None = Field(default=None)
    resolution_source: str = Field(description='Resolver or caller-provided coordinate source')


class AgentPlanningDecision(BaseModel):
    """Current first-choice night and observing location."""

    date: str
    location: StargazingLocation
    recommendation_score: float
    score_breakdown: ScoreBreakdown
    reason_summary: str | None = None
    observation_window: ObservationWindow | None = None
    targets: list[PlanningTarget] = Field(default_factory=list)
    equipment: ResolvedEquipment | None = None


class AgentPlanningAlternative(BaseModel):
    """Ranked alternative with an explicit comparison to the decision."""

    date: str
    location: StargazingLocation
    recommendation_score: float
    score_breakdown: ScoreBreakdown
    score_difference: float = Field(ge=0)
    comparison: dict[str, float] = Field(
        default_factory=dict,
        description='Signed component differences versus the selected decision',
    )


class EvidenceKind(StrEnum):
    """Stable evidence categories used by planning results."""

    PLACE = 'place'
    WEATHER = 'weather'
    SKY = 'sky'
    EQUIPMENT = 'equipment'


class PlanningEvidence(BaseModel):
    """A traceable fact group supporting the current decision."""

    kind: EvidenceKind
    source: str
    retrieved_at: str
    applies_to: str | None = None
    resource_id: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)


class UncertaintyLevel(StrEnum):
    """Impact level for a planning uncertainty."""

    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class PlanningUncertainty(BaseModel):
    """Known uncertainty or degraded dependency in the result."""

    code: str
    level: UncertaintyLevel
    message: str
    impact: str


class PlanningMissingInput(BaseModel):
    """Material caller information that could improve or change the decision."""

    field: str
    reason: str


class PlanningChangeCondition(BaseModel):
    """Condition that could reverse or materially alter the recommendation."""

    factor: str
    condition: str
    expected_effect: str


class PlanningNextAction(BaseModel):
    """Concrete follow-up that an agent or user can take."""

    action: str
    reason: str


class AgentPlanningResult(BaseModel):
    """Agent-native decision contract produced before MCP tool registration."""

    request: AgentPlanningRequest = Field(
        description='Normalized request with every default echoed'
    )
    resolved_location: ResolvedPlanningLocation
    decision: AgentPlanningDecision | None = None
    alternatives: list[AgentPlanningAlternative] = Field(default_factory=list)
    evidence: list[PlanningEvidence] = Field(default_factory=list)
    uncertainties: list[PlanningUncertainty] = Field(default_factory=list)
    missing_inputs: list[PlanningMissingInput] = Field(default_factory=list)
    would_change_if: list[PlanningChangeCondition] = Field(default_factory=list)
    next_actions: list[PlanningNextAction] = Field(default_factory=list)
