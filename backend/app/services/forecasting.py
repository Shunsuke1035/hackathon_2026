from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app.services.hotel_dependency import PREFECTURE_KEYWORDS, load_rows

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_FILE_DEFAULT = (
    PROJECT_ROOT
    / "data"
    / "hotel_allocation_biased"
    / "hotel_allocation_biased"
    / "scenario_event_shock_rates.csv"
)

MARKET_TO_SHOCK_COL = {
    "china": "shock_china",
    "korea": "shock_korea",
    "north_america": "shock_north_america",
    "southeast_asia": "shock_southeast_asia",
    "europe": "shock_europe",
    "japan": "shock_domestic_total",
}


@dataclass(frozen=True)
class ScenarioShock:
    event_id: str
    event_name_ja: str
    start_month: int
    end_month: int
    shock_values: dict[str, float]
    note: str


def _resolve_scenario_path() -> Path:
    env_path = os.getenv("SCENARIO_SHOCK_FILE")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
    if SCENARIO_FILE_DEFAULT.exists():
        return SCENARIO_FILE_DEFAULT
    raise FileNotFoundError(f"Scenario shock file not found: {SCENARIO_FILE_DEFAULT}")


def _read_dict_rows(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            with path.open("r", encoding=encoding, newline="") as fp:
                return list(csv.DictReader(fp))
        except Exception as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def _to_float(raw: str | None, default: float = 0.0) -> float:
    if raw is None:
        return default
    text = str(raw).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _to_int(raw: str | None, default: int = 0) -> int:
    return int(_to_float(raw, float(default)))


def _is_in_prefecture(address: str, ward: str, prefecture: str) -> bool:
    keywords = PREFECTURE_KEYWORDS.get(prefecture)
    if not keywords:
        return True
    text = f"{address}{ward}"
    return any(keyword in text for keyword in keywords)


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _add_months(year: int, month: int, step: int) -> tuple[int, int]:
    y = year
    m = month
    for _ in range(step):
        y, m = _next_month(y, m)
    return y, m


def _month_in_range(month: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= month <= end
    return month >= start or month <= end


@lru_cache(maxsize=1)
def load_scenarios() -> dict[str, ScenarioShock]:
    path = _resolve_scenario_path()
    rows = _read_dict_rows(path)
    out: dict[str, ScenarioShock] = {}
    for row in rows:
        event_id = (row.get("event_id") or "").strip()
        if not event_id:
            continue

        shock_values = {
            market: _to_float(row.get(shock_col), 0.0)
            for market, shock_col in MARKET_TO_SHOCK_COL.items()
        }
        out[event_id] = ScenarioShock(
            event_id=event_id,
            event_name_ja=(row.get("event_name_ja") or event_id).strip(),
            start_month=max(1, min(12, _to_int(row.get("start_month"), 1))),
            end_month=max(1, min(12, _to_int(row.get("end_month"), 12))),
            shock_values=shock_values,
            note=(row.get("note") or "").strip(),
        )
    return out


def list_available_scenarios() -> list[dict[str, str]]:
    return [
        {
            "event_id": scenario.event_id,
            "event_name_ja": scenario.event_name_ja,
            "note": scenario.note,
        }
        for scenario in load_scenarios().values()
    ]


def _market_total(prefecture: str, year: int, month: int, market: str) -> tuple[float, int]:
    _, rows = load_rows(month=month, year=year)
    total = 0.0
    active = 0
    for row in rows:
        if not _is_in_prefecture(row.address, row.ward, prefecture):
            continue
        value = float(row.markets.get(market, 0.0))
        total += value
        if value > 0:
            active += 1
    return total, active


def _safe_growth(current: float, prev: float | None) -> float:
    if prev is None or prev <= 0:
        return 0.0
    return (current - prev) / prev


def _seasonal_component(month: int) -> float:
    return 0.015 * math.sin((2 * math.pi * month) / 12.0)


def _clamp_growth(value: float) -> float:
    return max(-0.95, min(2.0, value))


def _estimate_baseline(prefecture: str, year: int, month: int, market: str) -> dict[str, float | int]:
    current_total, active_count = _market_total(prefecture, year, month, market)

    py, pm = _prev_month(year, month)
    prev_total: float | None
    try:
        prev_total, _ = _market_total(prefecture, py, pm, market)
    except FileNotFoundError:
        prev_total = None

    recent_growths: list[float] = []
    y, m = year, month
    current = current_total
    for _ in range(3):
        py, pm = _prev_month(y, m)
        try:
            prev, _ = _market_total(prefecture, py, pm, market)
        except FileNotFoundError:
            break
        recent_growths.append(_safe_growth(current, prev))
        y, m = py, pm
        current = prev

    baseline_growth = _safe_growth(current_total, prev_total)
    trend_growth = sum(recent_growths) / len(recent_growths) if recent_growths else baseline_growth

    return {
        "current_total": current_total,
        "prev_total": prev_total if prev_total is not None else 0.0,
        "active_facilities": active_count,
        "baseline_growth_rate": baseline_growth,
        "trend_growth_rate": trend_growth,
    }


def _shock_for_month(scenario: ScenarioShock, market: str, month: int) -> float:
    if not _month_in_range(month, scenario.start_month, scenario.end_month):
        return 0.0
    return float(scenario.shock_values.get(market, 0.0))


def _build_points(
    *,
    base_year: int,
    base_month: int,
    horizon_months: int,
    baseline_growth_rate: float,
    trend_growth_rate: float,
    shock_rate_fn: Callable[[int], float],
) -> list[dict[str, Any]]:
    prev_growth = baseline_growth_rate
    points: list[dict[str, Any]] = []
    for step in range(1, horizon_months + 1):
        year, month = _add_months(base_year, base_month, step)
        shock_rate = float(shock_rate_fn(month))
        seasonal = _seasonal_component(month)
        predicted = _clamp_growth(0.55 * prev_growth + 0.45 * (trend_growth_rate + seasonal + shock_rate))
        points.append(
            {
                "step": step,
                "year": year,
                "month": month,
                "month_date": f"{year:04d}-{month:02d}-01",
                "predicted_growth_rate": predicted,
                "applied_shock_rate": shock_rate,
                "seasonal_component": seasonal,
            }
        )
        prev_growth = predicted
    return points


def build_forecast_payload(
    *,
    prefecture: str,
    market: str,
    base_year: int | None,
    base_month: int,
    horizon_months: int,
    scenario_ids: list[str] | None = None,
    custom_shock_rate: float = 0.0,
) -> dict[str, Any]:
    if base_year is None:
        base_year, _ = load_rows(month=base_month, year=None)

    baseline = _estimate_baseline(prefecture, base_year, base_month, market)
    scenario_map = load_scenarios()

    selected_ids = scenario_ids or ["fx_jpy_depreciation", "infectious_disease_resurgence"]
    selected_ids = [scenario_id for scenario_id in selected_ids if scenario_id in scenario_map]

    scenarios: list[dict[str, Any]] = []
    base_points = _build_points(
        base_year=base_year,
        base_month=base_month,
        horizon_months=horizon_months,
        baseline_growth_rate=float(baseline["baseline_growth_rate"]),
        trend_growth_rate=float(baseline["trend_growth_rate"]),
        shock_rate_fn=lambda _month: 0.0,
    )
    scenarios.append(
        {
            "scenario_id": "base",
            "scenario_name_ja": "baseline",
            "note": "baseline case without external shock",
            "points": base_points,
        }
    )

    for scenario_id in selected_ids:
        scenario = scenario_map[scenario_id]
        points = _build_points(
            base_year=base_year,
            base_month=base_month,
            horizon_months=horizon_months,
            baseline_growth_rate=float(baseline["baseline_growth_rate"]),
            trend_growth_rate=float(baseline["trend_growth_rate"]),
            shock_rate_fn=lambda month, sc=scenario: _shock_for_month(sc, market, month) + custom_shock_rate,
        )
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_name_ja": scenario.event_name_ja,
                "note": scenario.note,
                "points": points,
            }
        )

    return {
        "model_version": "skeleton-v0.1",
        "target_metric": "guest_growth_rate",
        "prefecture": prefecture,
        "market": market,
        "base_year": base_year,
        "base_month": base_month,
        "horizon_months": horizon_months,
        "baseline_growth_rate": float(baseline["baseline_growth_rate"]),
        "feature_snapshot": baseline,
        "available_scenarios": list_available_scenarios(),
        "scenarios": scenarios,
    }
