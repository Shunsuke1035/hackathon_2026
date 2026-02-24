from __future__ import annotations

import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import enforce_rate_limit, get_current_user
from app.core.config import settings
from app.models.user import User
from app.services.dependency_metrics import build_dependency_metrics
from app.services.forecasting import build_forecast_payload, pick_simulation_scenario_ids
from app.services.hotel_dependency import build_dependency_points
from app.services.llm_recommendation import LLMRecommendationError, generate_recommendations_with_llm

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)
FORECAST_CACHE_TTL_SECONDS = 300
_FORECAST_CACHE: dict[str, tuple[float, dict]] = {}

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
    market_count: float | None = None
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
    market: MarketKey = "china"
    year: int | None = None


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
    facility_hhi_norm_active: float | None = None
    facility_entropy: float | None = None
    facility_entropy_norm_active: float | None = None
    facility_top1_share: float | None = None
    facility_top10_share: float | None = None
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
    facility_hhi_norm_active: float | None = None
    facility_entropy: float | None = None
    facility_entropy_norm_active: float | None = None
    facility_top1_share: float | None = None
    facility_top10_share: float | None = None
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


class ForecastPoint(BaseModel):
    step: int
    year: int
    month: int
    month_date: str
    predicted_growth_rate: float
    predicted_guest_count: float | None = None
    predicted_guest_count_total: float | None = None
    applied_shock_rate: float
    seasonal_component: float


class ForecastScenario(BaseModel):
    scenario_id: str
    scenario_name_ja: str
    note: str
    points: list[ForecastPoint]


class ForecastScenarioMeta(BaseModel):
    event_id: str
    event_name_ja: str
    note: str


class ForecastRequest(BaseModel):
    prefecture: str
    market: MarketKey = "china"
    year: int | None = None
    month: int = Field(ge=1, le=12)
    facility: FacilityInput | None = None
    horizon_months: int = Field(default=3, ge=1, le=24)
    scenario_ids: list[str] | None = None
    custom_shock_rate: float = 0.0


class ForecastResponse(BaseModel):
    model_version: str
    target_metric: str
    prefecture: str
    market: MarketKey
    base_year: int
    base_month: int
    horizon_months: int
    baseline_growth_rate: float
    feature_snapshot: dict[str, float | int]
    available_scenarios: list[ForecastScenarioMeta]
    scenarios: list[ForecastScenario]


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _collect_growth_rates_percent(
    forecast_payload: dict,
    target_scenario_ids: set[str] | None = None,
) -> list[float]:
    values: list[float] = []
    raw_scenarios = forecast_payload.get("scenarios", [])
    if not isinstance(raw_scenarios, list):
        return values

    for raw_scenario in raw_scenarios:
        if not isinstance(raw_scenario, dict):
            continue
        scenario_id = str(raw_scenario.get("scenario_id", ""))
        if target_scenario_ids is not None and scenario_id not in target_scenario_ids:
            continue

        raw_points = raw_scenario.get("points", [])
        if not isinstance(raw_points, list) or not raw_points:
            continue
        point_values = [
            float(point.get("predicted_growth_rate", 0.0))
            for point in raw_points
            if isinstance(point, dict)
        ]
        if not point_values:
            continue
        values.append(_mean(point_values) * 100.0)
    return values


def _get_forecast_payload_cached(
    *,
    prefecture: str,
    market: MarketKey,
    base_year: int | None,
    base_month: int,
    facility_lat: float | None = None,
    facility_lng: float | None = None,
    horizon_months: int,
    scenario_ids: list[str] | None,
    custom_shock_rate: float,
) -> dict:
    now = time.time()
    key = json.dumps(
        {
            "prefecture": prefecture,
            "market": market,
            "base_year": base_year,
            "base_month": base_month,
            "facility_lat": round(facility_lat, 6) if facility_lat is not None else None,
            "facility_lng": round(facility_lng, 6) if facility_lng is not None else None,
            "horizon_months": horizon_months,
            "scenario_ids": scenario_ids or [],
            "custom_shock_rate": custom_shock_rate,
        },
        ensure_ascii=True,
        sort_keys=True,
    )

    cached = _FORECAST_CACHE.get(key)
    if cached is not None and now - cached[0] <= FORECAST_CACHE_TTL_SECONDS:
        return cached[1]

    payload = build_forecast_payload(
        prefecture=prefecture,
        market=market,
        base_year=base_year,
        base_month=base_month,
        facility_lat=facility_lat,
        facility_lng=facility_lng,
        horizon_months=horizon_months,
        scenario_ids=scenario_ids,
        custom_shock_rate=custom_shock_rate,
    )
    _FORECAST_CACHE[key] = (now, payload)

    if len(_FORECAST_CACHE) > 128:
        stale_keys = [
            cache_key
            for cache_key, (saved_at, _) in _FORECAST_CACHE.items()
            if now - saved_at > FORECAST_CACHE_TTL_SECONDS
        ]
        for stale_key in stale_keys:
            _FORECAST_CACHE.pop(stale_key, None)

    return payload


@router.get("/dependency", response_model=DependencyResponse)
def get_dependency(
    prefecture: str,
    month: int = Query(default=1, ge=1, le=12),
    market: MarketKey | Literal["all"] = Query(default="all"),
    year: int | None = None,
    _: User = Depends(get_current_user),
) -> DependencyResponse:
    try:
        selected_year, raw_points = build_dependency_points(
            prefecture=prefecture,
            month=month,
            year=year,
            market=market,
            max_points=4000,
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


@router.post("/forecast", response_model=ForecastResponse)
def post_forecast(
    payload: ForecastRequest,
    _: User = Depends(get_current_user),
) -> ForecastResponse:
    try:
        forecast_payload = _get_forecast_payload_cached(
            prefecture=payload.prefecture,
            market=payload.market,
            base_year=payload.year,
            base_month=payload.month,
            facility_lat=payload.facility.lat if payload.facility else None,
            facility_lng=payload.facility.lng if payload.facility else None,
            horizon_months=payload.horizon_months,
            scenario_ids=payload.scenario_ids,
            custom_shock_rate=payload.custom_shock_rate,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    scenarios: list[ForecastScenario] = []
    for raw_scenario in forecast_payload.get("scenarios", []):
        if not isinstance(raw_scenario, dict):
            continue
        raw_points = raw_scenario.get("points", [])
        points = [
            ForecastPoint(**item)
            for item in raw_points
            if isinstance(item, dict)
        ]
        scenarios.append(
            ForecastScenario(
                scenario_id=str(raw_scenario.get("scenario_id", "")),
                scenario_name_ja=str(raw_scenario.get("scenario_name_ja", "")),
                note=str(raw_scenario.get("note", "")),
                points=points,
            )
        )

    metas = [
        ForecastScenarioMeta(**meta)
        for meta in forecast_payload.get("available_scenarios", [])
        if isinstance(meta, dict)
    ]

    return ForecastResponse(
        model_version=str(forecast_payload.get("model_version", "skeleton-v0.1")),
        target_metric=str(forecast_payload.get("target_metric", "guest_count")),
        prefecture=payload.prefecture,
        market=payload.market,
        base_year=int(forecast_payload.get("base_year", payload.year)),
        base_month=int(forecast_payload.get("base_month", payload.month)),
        horizon_months=int(forecast_payload.get("horizon_months", payload.horizon_months)),
        baseline_growth_rate=float(forecast_payload.get("baseline_growth_rate", 0.0)),
        feature_snapshot=dict(forecast_payload.get("feature_snapshot", {})),
        available_scenarios=metas,
        scenarios=scenarios,
    )


@router.post("/simulation", response_model=SimulationResponse)
def post_simulation(
    payload: SimulationRequest,
    _: User = Depends(get_current_user),
) -> SimulationResponse:
    base_case_ids: list[str] = []
    optimistic_ids, pessimistic_ids = pick_simulation_scenario_ids(
        market="china",
        month=payload.month,
        optimistic_limit=2,
        pessimistic_limit=2,
    )

    try:
        base_forecast = _get_forecast_payload_cached(
            prefecture=payload.prefecture,
            market="china",
            base_year=None,
            base_month=payload.month,
            facility_lat=payload.facility.lat,
            facility_lng=payload.facility.lng,
            horizon_months=3,
            scenario_ids=base_case_ids,
            custom_shock_rate=0.0,
        )
        optimistic_forecast = _get_forecast_payload_cached(
            prefecture=payload.prefecture,
            market="china",
            base_year=None,
            base_month=payload.month,
            facility_lat=payload.facility.lat,
            facility_lng=payload.facility.lng,
            horizon_months=3,
            scenario_ids=optimistic_ids,
            custom_shock_rate=0.05,
        )
        pessimistic_forecast = _get_forecast_payload_cached(
            prefecture=payload.prefecture,
            market="china",
            base_year=None,
            base_month=payload.month,
            facility_lat=payload.facility.lat,
            facility_lng=payload.facility.lng,
            horizon_months=3,
            scenario_ids=pessimistic_ids,
            custom_shock_rate=-0.05,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    base_values = _collect_growth_rates_percent(base_forecast, {"base"})
    optimistic_values = _collect_growth_rates_percent(optimistic_forecast, set(optimistic_ids))
    pessimistic_values = _collect_growth_rates_percent(pessimistic_forecast, set(pessimistic_ids))

    base_growth = round(_mean(base_values), 2)
    optimistic_growth = round(_mean(optimistic_values), 2) if optimistic_values else round(base_growth + 1.5, 2)
    pessimistic_growth = round(_mean(pessimistic_values), 2) if pessimistic_values else round(base_growth - 1.5, 2)
    scenario_name_map = {
        str(meta.get("event_id", "")): str(meta.get("event_name_ja", ""))
        for meta in base_forecast.get("available_scenarios", [])
        if isinstance(meta, dict)
    }
    optimistic_names = [scenario_name_map.get(sid, sid) for sid in optimistic_ids]
    pessimistic_names = [scenario_name_map.get(sid, sid) for sid in pessimistic_ids]

    scenarios = [
        SimulationScenario(
            name="optimistic",
            expected_growth_rate=optimistic_growth,
            risk_level="low",
            note=f"上振れシナリオ: {' / '.join(optimistic_names)}",
        ),
        SimulationScenario(
            name="base",
            expected_growth_rate=base_growth,
            risk_level="medium",
            note="ショックを含まないベースライン推移。",
        ),
        SimulationScenario(
            name="pessimistic",
            expected_growth_rate=pessimistic_growth,
            risk_level="high",
            note=f"下振れシナリオ: {' / '.join(pessimistic_names)}",
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
    request: Request,
    current_user: User = Depends(get_current_user),
) -> RecommendationResponse:
    client_host = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        scope="recommendation",
        identity=f"user:{current_user.id}|ip:{client_host}",
        max_requests=max(1, settings.recommendation_rate_limit_per_minute),
        window_seconds=60,
    )

    def fallback_items() -> list[RecommendationItem]:
        return [
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
        ]

    try:
        forecast_payload = _get_forecast_payload_cached(
            prefecture=payload.prefecture,
            market=payload.market,
            base_year=payload.year,
            base_month=payload.month,
            facility_lat=payload.facility.lat,
            facility_lng=payload.facility.lng,
            horizon_months=3,
            scenario_ids=None,
            custom_shock_rate=0.0,
        )
    except Exception:
        forecast_payload = {}

    try:
        metrics_payload = build_dependency_metrics(
            prefecture=payload.prefecture,
            month=payload.month,
            market=payload.market,
            year=payload.year,
        )
    except Exception:
        metrics_payload = None

    try:
        llm_items = generate_recommendations_with_llm(
            prefecture=payload.prefecture,
            month=payload.month,
            market=payload.market,
            forecast_payload=forecast_payload,
            metrics_payload=metrics_payload,
        )
        recommendations = [RecommendationItem(**item) for item in llm_items]
    except LLMRecommendationError as error:
        logger.warning("LLM recommendation fallback: %s", error)
        recommendations = fallback_items()
    except Exception as error:
        logger.exception("Unexpected recommendation generation error: %s", error)
        recommendations = fallback_items()

    return RecommendationResponse(
        prefecture=payload.prefecture,
        month=payload.month,
        recommendations=recommendations,
    )

