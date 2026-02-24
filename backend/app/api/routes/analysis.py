from hashlib import sha256
from random import Random

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/analysis", tags=["analysis"])

PREFECTURE_CENTERS: dict[str, tuple[float, float]] = {
    "kyoto": (35.0116, 135.7681),
    "tokyo": (35.6762, 139.6503),
    "hokkaido": (43.0642, 141.3469),
    "fukuoka": (33.5902, 130.4017),
    "okinawa": (26.2124, 127.6809),
    "osaka": (34.6937, 135.5023),
}

MARKETS = ["china", "north_america", "korea", "europe", "southeast_asia", "japan"]


class HeatPoint(BaseModel):
    lat: float
    lng: float
    dependency_score: float = Field(ge=0, le=1)
    market: str


class DependencyResponse(BaseModel):
    prefecture: str
    month: int
    points: list[HeatPoint]


class FacilityInput(BaseModel):
    lat: float
    lng: float
    address: str | None = None


class SimulationRequest(BaseModel):
    prefecture: str
    month: int = Field(ge=1, le=12)
    facility: FacilityInput


class SimulationScenario(BaseModel):
    name: str
    expected_growth_rate: float
    risk_level: str
    note: str


class SimulationResponse(BaseModel):
    prefecture: str
    month: int
    scenarios: list[SimulationScenario]


class RecommendationItem(BaseModel):
    type: str
    title: str
    description: str


class RecommendationRequest(BaseModel):
    prefecture: str
    month: int = Field(ge=1, le=12)
    facility: FacilityInput


class RecommendationResponse(BaseModel):
    prefecture: str
    month: int
    recommendations: list[RecommendationItem]


def _seed(prefecture: str, month: int) -> int:
    digest = sha256(f"{prefecture}:{month}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


@router.get("/dependency", response_model=DependencyResponse)
def get_dependency(
    prefecture: str,
    month: int = 1,
    _: User = Depends(get_current_user),
) -> DependencyResponse:
    center = PREFECTURE_CENTERS.get(prefecture, PREFECTURE_CENTERS["kyoto"])
    rnd = Random(_seed(prefecture, month))
    points: list[HeatPoint] = []
    for i in range(36):
        lat = center[0] + rnd.uniform(-0.12, 0.12)
        lng = center[1] + rnd.uniform(-0.12, 0.12)
        score = min(1.0, max(0.0, 0.25 + rnd.random() * 0.75))
        points.append(
            HeatPoint(
                lat=round(lat, 6),
                lng=round(lng, 6),
                dependency_score=round(score, 3),
                market=MARKETS[i % len(MARKETS)],
            )
        )
    return DependencyResponse(prefecture=prefecture, month=month, points=points)


@router.post("/simulation", response_model=SimulationResponse)
def post_simulation(
    payload: SimulationRequest,
    _: User = Depends(get_current_user),
) -> SimulationResponse:
    rnd = Random(_seed(payload.prefecture, payload.month) + 11)
    base = rnd.uniform(-2.0, 3.0)
    scenarios = [
        SimulationScenario(
            name="optimistic",
            expected_growth_rate=round(base + rnd.uniform(1.2, 2.8), 2),
            risk_level="low",
            note="Demand diversification and favorable exchange rates.",
        ),
        SimulationScenario(
            name="base",
            expected_growth_rate=round(base, 2),
            risk_level="medium",
            note="Current trend is sustained with moderate volatility.",
        ),
        SimulationScenario(
            name="pessimistic",
            expected_growth_rate=round(base - rnd.uniform(1.8, 3.4), 2),
            risk_level="high",
            note="High dependence segment declines under adverse external factors.",
        ),
    ]
    return SimulationResponse(
        prefecture=payload.prefecture,
        month=payload.month,
        scenarios=scenarios,
    )


@router.post("/recommendation", response_model=RecommendationResponse)
def post_recommendation(
    payload: RecommendationRequest,
    _: User = Depends(get_current_user),
) -> RecommendationResponse:
    return RecommendationResponse(
        prefecture=payload.prefecture,
        month=payload.month,
        recommendations=[
            RecommendationItem(
                type="risk_leverage",
                title="Focused campaign on high-yield segment",
                description=(
                    "Use monthly promotional bundles for the dominant market while setting "
                    "a dynamic price floor to control downside risk."
                ),
            ),
            RecommendationItem(
                type="risk_diversification",
                title="Diversify channels by travel purpose",
                description=(
                    "Increase share from non-dominant markets by creating packages for "
                    "family and long-stay travelers with localized messaging."
                ),
            ),
        ],
    )
