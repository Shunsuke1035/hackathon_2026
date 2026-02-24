from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
from joblib import load

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "lightgbm"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "forecasts"

DEFAULT_PANEL_OVERSEAS = DEFAULT_DATA_DIR / "panel_overseas_2025_with_features.csv"
DEFAULT_PANEL_CHINA = DEFAULT_DATA_DIR / "panel_chinease_2025_with_features.csv"
DEFAULT_EXOG = DEFAULT_DATA_DIR / "jnto_fx_merged_filled.csv"
DEFAULT_SCENARIO = DEFAULT_DATA_DIR / "scenario_event_shock_rates.csv"

TARGETS = {
    "overseas": {
        "target_col": "海外合計",
        "pred_col": "pred_海外合計",
        "lag1": "海外合計_lag1",
        "lag2": "海外合計_lag2",
        "roll3": "海外合計_rollmean3",
        "shock_col": "shock_overseas_total",
        "panel": DEFAULT_PANEL_OVERSEAS,
    },
    "china": {
        "target_col": "中国",
        "pred_col": "pred_中国",
        "lag1": "中国_lag1",
        "lag2": "中国_lag2",
        "roll3": "中国_rollmean3",
        "shock_col": "shock_china",
        "panel": DEFAULT_PANEL_CHINA,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run recursive scenario forecast with trained LightGBM models.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--exog-path", type=Path, default=DEFAULT_EXOG)
    parser.add_argument("--scenario-path", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--fx-rate-change", type=float, default=0.10)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_csv_fallback(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for enc in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def load_artifact(model_dir: Path, key: str) -> tuple[Any, dict[str, Any]]:
    model = load(model_dir / f"{key}_model.joblib")
    metadata = json.loads((model_dir / f"{key}_metadata.json").read_text(encoding="utf-8"))
    return model, metadata


def load_scenario_info(
    *,
    scenario_path: Path,
    event_id: str,
    target_shock_col: str,
    fx_rate_change: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    scen = read_csv_fallback(scenario_path)
    scen.columns = [str(col).strip() for col in scen.columns]
    row = scen.loc[scen["event_id"] == event_id]
    if row.empty:
        raise ValueError(f"event_id={event_id} was not found in {scenario_path}")
    item = row.iloc[0]

    multiplier: dict[str, float] = {}
    if target_shock_col in item and pd.notna(item[target_shock_col]):
        multiplier[target_shock_col] = 1.0 + float(item[target_shock_col])

    if event_id == "fx_jpy_appreciation":
        multiplier["usd_jpy"] = 1.0 - fx_rate_change
        multiplier["cny_jpy"] = 1.0 - fx_rate_change
    if event_id == "fx_jpy_depreciation":
        multiplier["usd_jpy"] = 1.0 + fx_rate_change
        multiplier["cny_jpy"] = 1.0 + fx_rate_change

    meta = {
        "event_id": event_id,
        "event_name_ja": str(item.get("event_name_ja", event_id)),
        "start_month": int(item.get("start_month", 1)),
        "end_month": int(item.get("end_month", 12)),
        "note": str(item.get("note", "")),
    }
    return multiplier, meta


def scenario_active(month: int, start_month: int, end_month: int) -> bool:
    if start_month <= end_month:
        return start_month <= month <= end_month
    return month >= start_month or month <= end_month


def select_exog_row(exog_df: pd.DataFrame, forecast_date: pd.Timestamp) -> pd.Series:
    exact = exog_df.loc[exog_df["date"] == forecast_date]
    if not exact.empty:
        return exact.iloc[-1]
    older = exog_df.loc[exog_df["date"] <= forecast_date]
    if not older.empty:
        return older.iloc[-1]
    return exog_df.iloc[-1]


def build_one_step_features(
    history: pd.DataFrame,
    *,
    forecast_date: pd.Timestamp,
    target_col: str,
    lag1_col: str,
    lag2_col: str,
    roll3_col: str,
    metadata: dict[str, Any],
    exog_values: dict[str, float],
) -> pd.DataFrame:
    sorted_history = history.sort_values(["facility_id", "date"]).copy()
    last = sorted_history.groupby("facility_id").tail(1).copy()

    lag1 = sorted_history.groupby("facility_id")[target_col].last().rename(lag1_col)
    lag2 = sorted_history.groupby("facility_id")[target_col].nth(-2).rename(lag2_col)
    roll3 = (
        sorted_history.groupby("facility_id")[target_col]
        .apply(lambda series: series.tail(3).mean())
        .rename(roll3_col)
    )

    base_cols = ["facility_id", "ward", "hotel_license_type", "room_scale", "latitude", "longitude"]
    keep_cols = [col for col in base_cols if col in last.columns]
    feat = last[keep_cols].drop_duplicates(subset=["facility_id"]).copy()
    feat = feat.merge(lag1, on="facility_id", how="left")
    feat = feat.merge(lag2, on="facility_id", how="left")
    feat = feat.merge(roll3, on="facility_id", how="left")

    feat["date"] = forecast_date
    feat["month_sin"] = math.sin(2.0 * math.pi * forecast_date.month / 12.0)
    feat["month_cos"] = math.cos(2.0 * math.pi * forecast_date.month / 12.0)

    for col, value in exog_values.items():
        feat[col] = value

    for col in metadata["feature_cols"]:
        if col not in feat.columns:
            feat[col] = 0.0
    return feat


def predict_recursive_for_target(
    *,
    panel_df: pd.DataFrame,
    model: Any,
    metadata: dict[str, Any],
    exog_df: pd.DataFrame,
    scenario_meta: dict[str, Any],
    scenario_multiplier: dict[str, float],
    start_date: pd.Timestamp,
    steps: int,
    cfg: dict[str, str],
) -> pd.DataFrame:
    history = panel_df.copy()
    history["date"] = pd.to_datetime(history["date"], errors="coerce").dt.normalize()
    history = history.dropna(subset=["date", "facility_id", cfg["target_col"]]).copy()

    outputs: list[pd.DataFrame] = []
    current_date = start_date

    for step in range(1, steps + 1):
        row = select_exog_row(exog_df, current_date)
        exog_values: dict[str, float] = {}
        for col in ("chinese_total", "visitors_overseas_total", "usd_jpy", "cny_jpy"):
            if col in row.index:
                exog_values[col] = float(row[col])

        if scenario_active(current_date.month, scenario_meta["start_month"], scenario_meta["end_month"]):
            if cfg["shock_col"] in scenario_multiplier and "visitors_overseas_total" in exog_values:
                exog_values["visitors_overseas_total"] *= float(scenario_multiplier[cfg["shock_col"]])
            if cfg["shock_col"] in scenario_multiplier and "chinese_total" in exog_values:
                exog_values["chinese_total"] *= float(scenario_multiplier[cfg["shock_col"]])
            for fx_col in ("usd_jpy", "cny_jpy"):
                if fx_col in scenario_multiplier and fx_col in exog_values:
                    exog_values[fx_col] *= float(scenario_multiplier[fx_col])

        feature_frame = build_one_step_features(
            history,
            forecast_date=current_date,
            target_col=cfg["target_col"],
            lag1_col=cfg["lag1"],
            lag2_col=cfg["lag2"],
            roll3_col=cfg["roll3"],
            metadata=metadata,
            exog_values=exog_values,
        )

        x = feature_frame[metadata["feature_cols"]].copy()
        for col in metadata.get("categorical_cols", []):
            if col in x.columns:
                x[col] = x[col].astype(str).fillna("unknown").astype("category")
        for col in metadata["feature_cols"]:
            if col in metadata.get("categorical_cols", []):
                continue
            x[col] = pd.to_numeric(x[col], errors="coerce").fillna(0.0)

        pred = model.predict(x, num_iteration=getattr(model, "best_iteration_", None))
        out = pd.DataFrame(
            {
                "facility_id": feature_frame["facility_id"],
                "date": current_date,
                "step": step,
                cfg["pred_col"]: pred,
            }
        )
        outputs.append(out)

        append = feature_frame.copy()
        append[cfg["target_col"]] = pred
        history = pd.concat([history, append], ignore_index=True, sort=False)
        current_date = (current_date + pd.offsets.MonthBegin(1)).normalize()

    return pd.concat(outputs, ignore_index=True)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    exog_df = read_csv_fallback(args.exog_path)
    exog_df["date"] = pd.to_datetime(exog_df["date"], errors="coerce").dt.normalize()
    exog_df = exog_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    start_date = pd.to_datetime(args.start_date).normalize()

    forecasts = []
    for key, cfg in TARGETS.items():
        panel_df = read_csv_fallback(cfg["panel"])
        model, metadata = load_artifact(args.model_dir, key)
        scenario_multiplier, scenario_meta = load_scenario_info(
            scenario_path=args.scenario_path,
            event_id=args.event_id,
            target_shock_col=cfg["shock_col"],
            fx_rate_change=args.fx_rate_change,
        )

        pred = predict_recursive_for_target(
            panel_df=panel_df,
            model=model,
            metadata=metadata,
            exog_df=exog_df,
            scenario_meta=scenario_meta,
            scenario_multiplier=scenario_multiplier,
            start_date=start_date,
            steps=args.steps,
            cfg=cfg,
        )
        forecasts.append(pred)

    merged = forecasts[0]
    for frame in forecasts[1:]:
        merged = merged.merge(frame, on=["facility_id", "date", "step"], how="outer")

    out_path = args.output_dir / f"forecast_{args.event_id}_{start_date.strftime('%Y%m')}_steps{args.steps}.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"saved: {out_path}")
    print(f"rows : {len(merged)}")


if __name__ == "__main__":
    main()
