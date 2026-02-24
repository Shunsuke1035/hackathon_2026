from __future__ import annotations

from hashlib import sha256
from random import Random
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.services.dependency_metrics import build_dependency_metrics
from app.services.hotel_dependency import build_dependency_points

router = APIRouter(prefix="/analysis", tags=["analysis"])

PREFECTURE_CENTERS: dict[str, tuple[float, float]] = {
    "kyoto": (35.0116, 135.7681),
    "tokyo": (35.6762, 139.6503),
    "hokkaido": (43.0642, 141.3469),
    "fukuoka": (33.5902, 130.4017),
    "okinawa": (26.2124, 127.6809),
    "osaka": (34.6937, 135.5023),
}


class HeatPoint(BaseModel):
    lat: float
    lng: float
    dependency_score: float = Field(ge=0, le=1)
    market: str


class DependencyResponse(BaseModel):
    prefecture: str
    month: int
    year: int
    points: list[HeatPoint]
    note: str | None = None


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


MarketKey = Literal["china", "korea", "north_america", "southeast_asia", "europe", "japan"]


class DependencyMetricsSeriesPoint(BaseModel):
    year: int
    month: int
    month_date: str
    market_total: float
    facility_count_total: int
    facility_count_active: int
    facility_hhi: float | None = None
    facility_entropy: float | None = None
    facility_entropy_norm_active: float | None = None
    facility_top1_share: float | None = None
    foreign_hhi: float | None = None
    foreign_entropy: float | None = None
    foreign_entropy_norm: float | None = None
    all_hhi: float | None = None
    all_entropy: float | None = None
    all_entropy_norm: float | None = None


class DependencyMetricsCurrent(BaseModel):
    year: int
    month: int
    month_date: str
    selected_market: MarketKey
    market_total: float
    facility_count_total: int
    facility_count_active: int
    facility_hhi: float | None = None
    facility_entropy: float | None = None
    facility_entropy_norm_active: float | None = None
    facility_top1_share: float | None = None
    foreign_hhi: float | None = None
    foreign_entropy: float | None = None
    foreign_entropy_norm: float | None = None
    foreign_top1_market: str | None = None
    foreign_top1_share: float | None = None
    all_hhi: float | None = None
    all_entropy: float | None = None
    all_entropy_norm: float | None = None
    all_top1_market: str | None = None
    all_top1_share: float | None = None


class DependencyMetricsResponse(BaseModel):
    prefecture: str
    month: int
    year: int
    market: MarketKey
    current: DependencyMetricsCurrent
    series: list[DependencyMetricsSeriesPoint]
    note: str | None = None


def _seed(prefecture: str, month: int) -> int:
    digest = sha256(f"{prefecture}:{month}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


@router.get("/dependency", response_model=DependencyResponse)
def get_dependency(
    prefecture: str,
    month: int = Query(default=1, ge=1, le=12),
    year: int | None = None,
    _: User = Depends(get_current_user),
) -> DependencyResponse:
    try:
        selected_year, raw_points = build_dependency_points(
            prefecture=prefecture,
            month=month,
            year=year,
            max_points=2500,
        )
    except FileNotFoundError:
        return DependencyResponse(
            prefecture=prefecture,
            month=month,
            year=year or 0,
            points=[],
            note="対象月のデータファイルが見つかりませんでした。",
        )

    points = [HeatPoint(**item) for item in raw_points]

    note: str | None = None
    if prefecture != "kyoto" and not points:
        note = "現在の正式データは京都府中心のため、選択地域では表示点が少ない可能性があります。"

    return DependencyResponse(
        prefecture=prefecture,
        month=month,
        year=selected_year,
        points=points,
        note=note,
    )


@router.get("/dependency-metrics", response_model=DependencyMetricsResponse)
def get_dependency_metrics(
    prefecture: str,
    month: int = Query(default=1, ge=1, le=12),
    market: MarketKey = Query(default="china"),
    year: int | None = None,
    _: User = Depends(get_current_user),
) -> DependencyMetricsResponse:
    try:
        payload = build_dependency_metrics(
            prefecture=prefecture,
            month=month,
            market=market,
            year=year,
        )
    except FileNotFoundError:
        return DependencyMetricsResponse(
            prefecture=prefecture,
            month=month,
            year=year or 0,
            market=market,
            current=DependencyMetricsCurrent(
                year=year or 0,
                month=month,
                month_date=f"{year or 0:04d}-{month:02d}-01",
                selected_market=market,
                market_total=0.0,
                facility_count_total=0,
                facility_count_active=0,
            ),
            series=[],
            note="依存度メトリクスの集計対象データが見つかりませんでした。",
        )

    note: str | None = None
    if prefecture != "kyoto" and not payload["series"]:
        note = "選択地域のデータが不足しているため、表示内容が限定される可能性があります。"

    return DependencyMetricsResponse(
        prefecture=prefecture,
        month=month,
        year=payload["current_year"],
        market=market,
        current=DependencyMetricsCurrent(**payload["current"]),
        series=[DependencyMetricsSeriesPoint(**item) for item in payload["series"]],
        note=note,
    )


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
            note="訪日需要が回復したケース。価格と稼働率の同時改善を想定。",
        ),
        SimulationScenario(
            name="base",
            expected_growth_rate=round(base, 2),
            risk_level="medium",
            note="現状トレンドが継続するケース。需要は横ばいから緩やかな改善。",
        ),
        SimulationScenario(
            name="pessimistic",
            expected_growth_rate=round(base - rnd.uniform(1.8, 3.4), 2),
            risk_level="high",
            note="外部ショックが発生するケース。需要減少に備えた運営が必要。",
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
                title="依存市場の強みを活かす価格設計",
                description=(
                    "主要国籍向けに販売チャネルと訴求内容を最適化し、"
                    "繁忙期の単価向上と閑散期の稼働維持を両立します。"
                ),
            ),
            RecommendationItem(
                type="risk_diversification",
                title="依存度分散のための販路再配分",
                description=(
                    "高依存市場に偏った集客を見直し、滞在目的が異なる市場へ"
                    "広告配分と商品構成を段階的に移行します。"
                ),
            ),
        ],
    )

