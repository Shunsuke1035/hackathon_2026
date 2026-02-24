from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app.services.hotel_dependency import PREFECTURE_KEYWORDS, load_rows

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased"
SCENARIO_FILE_DEFAULT = DATA_DIR / "scenario_event_shock_rates.csv"
EXOG_FILE_DEFAULT = DATA_DIR / "jnto_fx_merged_filled.csv"
PANEL_FILE_DEFAULTS = {
    "china": DATA_DIR / "panel_chinease_2025_with_features.csv",
    "overseas": DATA_DIR / "panel_overseas_2025_with_features.csv",
}
MODEL_DIR_DEFAULT = PROJECT_ROOT / "models" / "lightgbm"

MARKET_TO_SHOCK_COL = {
    "china": "shock_china",
    "korea": "shock_korea",
    "north_america": "shock_north_america",
    "southeast_asia": "shock_southeast_asia",
    "europe": "shock_europe",
    "japan": "shock_domestic_total",
}

TARGET_CONFIG = {
    "china": {
        "target_col": "中国",
        "lag1_col": "中国_lag1",
        "lag2_col": "中国_lag2",
        "roll3_col": "中国_rollmean3",
        "model_key": "china",
    },
    "overseas": {
        "target_col": "海外合計",
        "lag1_col": "海外合計_lag1",
        "lag2_col": "海外合計_lag2",
        "roll3_col": "海外合計_rollmean3",
        "model_key": "overseas",
    },
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


def _resolve_exog_path() -> Path:
    env_path = os.getenv("FORECAST_EXOG_FILE")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
    if EXOG_FILE_DEFAULT.exists():
        return EXOG_FILE_DEFAULT
    raise FileNotFoundError(f"Exogenous feature file not found: {EXOG_FILE_DEFAULT}")


def _resolve_panel_path(model_key: str) -> Path:
    env_name = "FORECAST_PANEL_CHINA" if model_key == "china" else "FORECAST_PANEL_OVERSEAS"
    env_path = os.getenv(env_name)
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    path = PANEL_FILE_DEFAULTS[model_key]
    if path.exists():
        return path
    raise FileNotFoundError(f"Panel file not found for {model_key}: {path}")


def _resolve_model_dir() -> Path:
    env_path = os.getenv("FORECAST_MODEL_DIR")
    if env_path:
        path = Path(env_path)
        if path.exists() and path.is_dir():
            return path
    return MODEL_DIR_DEFAULT


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


def _target_key_from_market(market: str) -> str:
    if market == "china":
        return "china"
    return "overseas"


def _safe_growth(current: float, prev: float | None) -> float:
    if prev is None or prev <= 0:
        return 0.0
    return (current - prev) / prev


def _seasonal_component(month: int) -> float:
    return 0.015 * math.sin((2 * math.pi * month) / 12.0)


def _clamp_growth(value: float) -> float:
    return max(-0.95, min(2.0, value))


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


def _build_points_skeleton(
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


def _build_forecast_payload_skeleton(
    *,
    prefecture: str,
    market: str,
    base_year: int | None,
    base_month: int,
    horizon_months: int,
    scenario_ids: list[str] | None,
    custom_shock_rate: float,
) -> dict[str, Any]:
    if base_year is None:
        base_year, _ = load_rows(month=base_month, year=None)

    baseline = _estimate_baseline(prefecture, base_year, base_month, market)
    scenario_map = load_scenarios()

    selected_ids = scenario_ids or ["fx_jpy_depreciation", "infectious_disease_resurgence"]
    selected_ids = [scenario_id for scenario_id in selected_ids if scenario_id in scenario_map]

    scenarios: list[dict[str, Any]] = []
    base_points = _build_points_skeleton(
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
        points = _build_points_skeleton(
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


def _check_ml_dependencies() -> bool:
    required = ("pandas", "joblib", "lightgbm")
    for module_name in required:
        if importlib.util.find_spec(module_name) is None:
            return False
    return True


@lru_cache(maxsize=1)
def _pd() -> Any:
    return importlib.import_module("pandas")


@lru_cache(maxsize=1)
def _joblib_load() -> Callable[[Path], Any]:
    module = importlib.import_module("joblib")
    return module.load


def _read_csv_fallback(path: Path) -> Any:
    pd = _pd()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


@lru_cache(maxsize=2)
def _load_panel_df(model_key: str) -> Any:
    path = _resolve_panel_path(model_key)
    frame = _read_csv_fallback(path)
    pd = _pd()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    elif "year" in frame.columns and "month" in frame.columns:
        frame["date"] = pd.to_datetime(
            frame["year"].astype(str) + "-" + frame["month"].astype(str) + "-01",
            errors="coerce",
        )
    else:
        raise ValueError(f"date columns are missing in panel file: {path}")

    frame = frame.dropna(subset=["date", "facility_id"]).copy()
    frame["date"] = frame["date"].dt.normalize()
    return frame


@lru_cache(maxsize=1)
def _load_exog_df() -> Any:
    pd = _pd()
    path = _resolve_exog_path()
    frame = _read_csv_fallback(path)
    if "date" not in frame.columns:
        raise ValueError(f"date column is missing in exogenous file: {path}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).copy()
    frame["date"] = frame["date"].dt.normalize()
    frame = frame.sort_values("date").reset_index(drop=True)
    return frame


@lru_cache(maxsize=2)
def _load_model_artifact(model_key: str) -> tuple[Any, dict[str, Any]]:
    model_dir = _resolve_model_dir()
    model_path = model_dir / f"{model_key}_model.joblib"
    meta_path = model_dir / f"{model_key}_metadata.json"
    if not model_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"model artifacts not found for {model_key} in {model_dir}")

    model = _joblib_load()(model_path)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return model, metadata


def _filter_prefecture_df(frame: Any, prefecture: str) -> Any:
    keywords = PREFECTURE_KEYWORDS.get(prefecture)
    if not keywords:
        return frame.copy()

    address = frame.get("address", "")
    ward = frame.get("ward", "")
    text = address.fillna("").astype(str) + ward.fillna("").astype(str)
    mask = text.apply(lambda value: any(keyword in value for keyword in keywords))
    filtered = frame.loc[mask].copy()
    return filtered


def _pick_base_date(frame: Any, base_year: int | None, base_month: int) -> tuple[Any, int, int]:
    pd = _pd()
    working = frame.copy()
    working["year_i"] = working["date"].dt.year
    working["month_i"] = working["date"].dt.month

    if base_year is None:
        candidates = working.loc[working["month_i"] == base_month]
        if not candidates.empty:
            base_year = int(candidates["year_i"].max())
        else:
            base_year = int(working["year_i"].max())

    target_date = pd.Timestamp(year=base_year, month=base_month, day=1)
    exact = working.loc[working["date"] == target_date]
    if exact.empty:
        candidates = working.loc[working["date"] <= target_date]
        if candidates.empty:
            target_date = working["date"].max()
        else:
            target_date = candidates["date"].max()

    return target_date.normalize(), int(target_date.year), int(target_date.month)


def _select_exog_row(exog_df: Any, forecast_date: Any) -> dict[str, float]:
    exog_cols = ["chinese_total", "visitors_overseas_total", "usd_jpy", "cny_jpy"]
    row = exog_df.loc[exog_df["date"] == forecast_date]
    if row.empty:
        row = exog_df.loc[exog_df["date"] <= forecast_date].tail(1)
    if row.empty:
        row = exog_df.tail(1)

    out: dict[str, float] = {}
    if row.empty:
        return out
    item = row.iloc[-1]
    for col in exog_cols:
        if col in item.index:
            out[col] = _to_float(item[col], 0.0)
    return out


def _build_step_features(
    history: Any,
    *,
    forecast_date: Any,
    target_col: str,
    lag1_col: str,
    lag2_col: str,
    roll3_col: str,
    metadata: dict[str, Any],
    exog_values: dict[str, float],
) -> Any:
    sorted_history = history.sort_values(["facility_id", "date"]).copy()
    grouped = sorted_history.groupby("facility_id")[target_col]

    base_cols = ["facility_id", "ward", "hotel_license_type", "room_scale", "latitude", "longitude"]
    available_base_cols = [col for col in base_cols if col in sorted_history.columns]
    last = sorted_history.groupby("facility_id").tail(1)[available_base_cols].copy()

    lag1 = grouped.last().rename(lag1_col).reset_index()
    lag2 = grouped.apply(lambda series: series.iloc[-2] if len(series) >= 2 else float("nan")).rename(lag2_col).reset_index()
    roll3 = grouped.apply(lambda series: series.tail(3).mean()).rename(roll3_col).reset_index()

    feat = last.merge(lag1, on="facility_id", how="left")
    feat = feat.merge(lag2, on="facility_id", how="left")
    feat = feat.merge(roll3, on="facility_id", how="left")

    feat["date"] = forecast_date
    feat["month_sin"] = math.sin(2.0 * math.pi * forecast_date.month / 12.0)
    feat["month_cos"] = math.cos(2.0 * math.pi * forecast_date.month / 12.0)

    for col, value in exog_values.items():
        feat[col] = value

    feature_cols = list(metadata.get("feature_cols", []))
    for col in feature_cols:
        if col not in feat.columns:
            feat[col] = 0.0

    return feat


def _predict_recursive_points(
    *,
    history: Any,
    model: Any,
    metadata: dict[str, Any],
    scenario: ScenarioShock | None,
    market: str,
    base_date: Any,
    horizon_months: int,
    custom_shock_rate: float,
    target_config: dict[str, str],
) -> tuple[list[dict[str, Any]], float, dict[str, float | int]]:
    pd = _pd()
    target_col = target_config["target_col"]
    lag1_col = target_config["lag1_col"]
    lag2_col = target_config["lag2_col"]
    roll3_col = target_config["roll3_col"]

    working = history.copy()
    working = working.dropna(subset=[target_col]).copy()

    base_rows = working.loc[working["date"] == base_date]
    if base_rows.empty:
        base_rows = working.loc[working["date"] <= base_date]
    if base_rows.empty:
        raise ValueError("no history rows are available for forecast base")

    base_total = float(base_rows.groupby("date")[target_col].sum().iloc[-1])

    prev_date = (base_date - pd.offsets.MonthBegin(1)).normalize()
    prev_rows = working.loc[working["date"] == prev_date]
    prev_total = float(prev_rows[target_col].sum()) if not prev_rows.empty else base_total
    baseline_growth = _safe_growth(base_total, prev_total if prev_total > 0 else None)

    points: list[dict[str, Any]] = []
    prev_total_for_growth = base_total
    exog_df = _load_exog_df()

    for step in range(1, horizon_months + 1):
        forecast_date = (base_date + pd.offsets.MonthBegin(step)).normalize()
        exog_values = _select_exog_row(exog_df, forecast_date)

        shock_rate = 0.0
        if scenario is not None:
            shock_rate = _shock_for_month(scenario, market, forecast_date.month) + custom_shock_rate

        if market == "china":
            if "chinese_total" in exog_values:
                exog_values["chinese_total"] *= 1.0 + shock_rate
        else:
            if "visitors_overseas_total" in exog_values:
                exog_values["visitors_overseas_total"] *= 1.0 + shock_rate

        if scenario is not None:
            if scenario.event_id == "fx_jpy_appreciation":
                if "usd_jpy" in exog_values:
                    exog_values["usd_jpy"] *= 0.9
                if "cny_jpy" in exog_values:
                    exog_values["cny_jpy"] *= 0.9
            if scenario.event_id == "fx_jpy_depreciation":
                if "usd_jpy" in exog_values:
                    exog_values["usd_jpy"] *= 1.1
                if "cny_jpy" in exog_values:
                    exog_values["cny_jpy"] *= 1.1

        feature_frame = _build_step_features(
            working,
            forecast_date=forecast_date,
            target_col=target_col,
            lag1_col=lag1_col,
            lag2_col=lag2_col,
            roll3_col=roll3_col,
            metadata=metadata,
            exog_values=exog_values,
        )

        feature_cols = list(metadata.get("feature_cols", []))
        categorical_cols = list(metadata.get("categorical_cols", []))

        x = feature_frame[feature_cols].copy()
        for col in categorical_cols:
            if col in x.columns:
                x[col] = x[col].astype(str).fillna("unknown").astype("category")

        for col in feature_cols:
            if col in categorical_cols:
                continue
            x[col] = _pd().to_numeric(x[col], errors="coerce").fillna(0.0)

        pred = model.predict(x, num_iteration=getattr(model, "best_iteration_", None))
        pred_series = _pd().Series(pred).fillna(0.0).clip(lower=0.0)

        predicted_total = float(pred_series.sum())
        growth_rate = _safe_growth(predicted_total, prev_total_for_growth)

        points.append(
            {
                "step": step,
                "year": int(forecast_date.year),
                "month": int(forecast_date.month),
                "month_date": f"{forecast_date.year:04d}-{forecast_date.month:02d}-01",
                "predicted_growth_rate": growth_rate,
                "applied_shock_rate": shock_rate,
                "seasonal_component": 0.0,
            }
        )

        append = feature_frame[["facility_id", "date"]].copy()
        append[target_col] = pred_series.to_numpy()
        for col in ("ward", "hotel_license_type", "room_scale", "latitude", "longitude"):
            if col in feature_frame.columns:
                append[col] = feature_frame[col]

        working = _pd().concat([working, append], ignore_index=True, sort=False)
        prev_total_for_growth = predicted_total

    snapshot = {
        "base_total": base_total,
        "prev_total": prev_total,
        "facility_count": int(base_rows["facility_id"].nunique()),
        "baseline_growth_rate": baseline_growth,
    }
    return points, baseline_growth, snapshot


def _build_forecast_payload_lightgbm(
    *,
    prefecture: str,
    market: str,
    base_year: int | None,
    base_month: int,
    horizon_months: int,
    scenario_ids: list[str] | None,
    custom_shock_rate: float,
) -> dict[str, Any]:
    target_key = _target_key_from_market(market)
    target_config = TARGET_CONFIG[target_key]

    panel = _load_panel_df(target_config["model_key"])
    filtered = _filter_prefecture_df(panel, prefecture)
    used_prefecture_fallback = 0
    if filtered.empty:
        filtered = panel.copy()
        used_prefecture_fallback = 1

    base_date, resolved_year, resolved_month = _pick_base_date(filtered, base_year, base_month)

    model, metadata = _load_model_artifact(target_config["model_key"])
    scenario_map = load_scenarios()
    selected_ids = scenario_ids or ["fx_jpy_depreciation", "infectious_disease_resurgence"]
    selected_ids = [scenario_id for scenario_id in selected_ids if scenario_id in scenario_map]

    base_points, baseline_growth, base_snapshot = _predict_recursive_points(
        history=filtered,
        model=model,
        metadata=metadata,
        scenario=None,
        market=market,
        base_date=base_date,
        horizon_months=horizon_months,
        custom_shock_rate=custom_shock_rate,
        target_config=target_config,
    )

    scenarios = [
        {
            "scenario_id": "base",
            "scenario_name_ja": "baseline",
            "note": "baseline case without external shock",
            "points": base_points,
        }
    ]

    for scenario_id in selected_ids:
        scenario = scenario_map[scenario_id]
        scenario_points, _, _ = _predict_recursive_points(
            history=filtered,
            model=model,
            metadata=metadata,
            scenario=scenario,
            market=market,
            base_date=base_date,
            horizon_months=horizon_months,
            custom_shock_rate=custom_shock_rate,
            target_config=target_config,
        )
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_name_ja": scenario.event_name_ja,
                "note": scenario.note,
                "points": scenario_points,
            }
        )

    feature_snapshot = {
        "base_total": float(base_snapshot["base_total"]),
        "prev_total": float(base_snapshot["prev_total"]),
        "facility_count": int(base_snapshot["facility_count"]),
        "target_key": 1 if target_key == "china" else 2,
        "used_prefecture_fallback": used_prefecture_fallback,
    }

    return {
        "model_version": "lightgbm-v1",
        "target_metric": "guest_growth_rate",
        "prefecture": prefecture,
        "market": market,
        "base_year": resolved_year,
        "base_month": resolved_month,
        "horizon_months": horizon_months,
        "baseline_growth_rate": float(baseline_growth),
        "feature_snapshot": feature_snapshot,
        "available_scenarios": list_available_scenarios(),
        "scenarios": scenarios,
    }


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
    if _check_ml_dependencies():
        try:
            return _build_forecast_payload_lightgbm(
                prefecture=prefecture,
                market=market,
                base_year=base_year,
                base_month=base_month,
                horizon_months=horizon_months,
                scenario_ids=scenario_ids,
                custom_shock_rate=custom_shock_rate,
            )
        except Exception:
            # Fallback keeps API available even before model artifacts are prepared.
            pass

    return _build_forecast_payload_skeleton(
        prefecture=prefecture,
        market=market,
        base_year=base_year,
        base_month=base_month,
        horizon_months=horizon_months,
        scenario_ids=scenario_ids,
        custom_shock_rate=custom_shock_rate,
    )
