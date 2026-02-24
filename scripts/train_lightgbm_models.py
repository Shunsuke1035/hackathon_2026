from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.metrics import mean_squared_error

try:
    import lightgbm as lgb
except ModuleNotFoundError as error:  # pragma: no cover
    raise SystemExit(
        "lightgbm is not installed. Run: pip install lightgbm"
    ) from error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "lightgbm"

DEFAULT_OVERSEAS_PANEL = DEFAULT_DATA_DIR / "panel_overseas_2025_with_features.csv"
DEFAULT_CHINA_PANEL = DEFAULT_DATA_DIR / "panel_chinease_2025_with_features.csv"

EXOG_CANDIDATES = ["chinese_total", "visitors_overseas_total", "usd_jpy", "cny_jpy"]
TIME_CANDIDATES = ["month_sin", "month_cos"]
STATIC_CANDIDATES = ["room_scale", "latitude", "longitude"]
CATEGORICAL_CANDIDATES = ["ward", "hotel_license_type"]

TARGET_CONFIG = {
    "overseas": {
        "target_col": "海外合計",
        "lag_cols": ["海外合計_lag1", "海外合計_lag2"],
        "roll_cols": ["海外合計_rollmean3"],
    },
    "china": {
        "target_col": "中国",
        "lag_cols": ["中国_lag1", "中国_lag2"],
        "roll_cols": ["中国_rollmean3"],
    },
}


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LightGBM models for tourism forecasting.")
    parser.add_argument("--panel-overseas", type=Path, default=DEFAULT_OVERSEAS_PANEL)
    parser.add_argument("--panel-china", type=Path, default=DEFAULT_CHINA_PANEL)
    parser.add_argument("--test-start", default="2025-01-01")
    parser.add_argument("--test-end", default="2025-06-01")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def ensure_date_col(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    elif "year" in out.columns and "month" in out.columns:
        out["date"] = pd.to_datetime(
            out["year"].astype(int).astype(str) + "-" + out["month"].astype(int).astype(str) + "-01",
            errors="coerce",
        )
    else:
        raise ValueError("date column is missing and cannot be constructed from year/month")

    out = out.dropna(subset=["date"]).copy()
    out["date"] = out["date"].dt.normalize()
    return out


def ensure_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "month_sin" not in out.columns:
        out["month_sin"] = np.sin(2 * np.pi * out["date"].dt.month / 12.0)
    if "month_cos" not in out.columns:
        out["month_cos"] = np.cos(2 * np.pi * out["date"].dt.month / 12.0)
    return out


def ensure_lag_roll_features(frame: pd.DataFrame, target_col: str, lag_cols: list[str], roll_cols: list[str]) -> pd.DataFrame:
    out = frame.sort_values(["facility_id", "date"]).copy()
    grouped = out.groupby("facility_id")[target_col]

    if lag_cols:
        lag_map = {
            lag_cols[0]: 1,
            lag_cols[1]: 2,
        }
        for col_name, lag_n in lag_map.items():
            if col_name not in out.columns:
                out[col_name] = grouped.shift(lag_n)

    if roll_cols and roll_cols[0] not in out.columns:
        out[roll_cols[0]] = grouped.shift(1).rolling(3, min_periods=1).mean()

    return out


def build_feature_cols(frame: pd.DataFrame, target_key: str) -> tuple[list[str], list[str]]:
    cfg = TARGET_CONFIG[target_key]
    candidates = (
        EXOG_CANDIDATES
        + TIME_CANDIDATES
        + cfg["lag_cols"]
        + cfg["roll_cols"]
        + STATIC_CANDIDATES
        + CATEGORICAL_CANDIDATES
    )
    feature_cols = [col for col in candidates if col in frame.columns]
    categorical_cols = [col for col in CATEGORICAL_CANDIDATES if col in feature_cols]
    return feature_cols, categorical_cols


def fit_one(
    frame: pd.DataFrame,
    *,
    target_key: str,
    test_start: str,
    test_end: str,
    seed: int,
) -> tuple[lgb.LGBMRegressor, dict[str, Any], pd.DataFrame]:
    cfg = TARGET_CONFIG[target_key]
    target_col = cfg["target_col"]

    df = ensure_date_col(frame)
    df = ensure_time_features(df)
    df = ensure_lag_roll_features(df, target_col, cfg["lag_cols"], cfg["roll_cols"])
    df = df.sort_values(["facility_id", "date"]).copy()

    feature_cols, categorical_cols = build_feature_cols(df, target_key)

    model_df = df.dropna(subset=[target_col]).copy()
    test_mask = (model_df["date"] >= pd.Timestamp(test_start)) & (model_df["date"] <= pd.Timestamp(test_end))
    train_df = model_df.loc[~test_mask].copy()
    test_df = model_df.loc[test_mask].copy()
    if train_df.empty or test_df.empty:
        raise ValueError(f"invalid train/test split for target={target_col}")

    x_train = train_df[feature_cols].copy()
    x_test = test_df[feature_cols].copy()
    y_train = train_df[target_col].astype(float)
    y_test = test_df[target_col].astype(float)

    for col in categorical_cols:
        x_train[col] = x_train[col].astype(str).fillna("unknown").astype("category")
        x_test[col] = x_test[col].astype(str).fillna("unknown").astype("category")

    for col in feature_cols:
        if col in categorical_cols:
            continue
        x_train[col] = pd.to_numeric(x_train[col], errors="coerce").fillna(0.0)
        x_test[col] = pd.to_numeric(x_test[col], errors="coerce").fillna(0.0)

    model = lgb.LGBMRegressor(
        objective="regression",
        learning_rate=0.03,
        num_leaves=63,
        n_estimators=4000,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_train, y_train), (x_test, y_test)],
        eval_metric="rmse",
        categorical_feature=categorical_cols if categorical_cols else "auto",
        callbacks=[lgb.early_stopping(stopping_rounds=200, verbose=False)],
    )

    pred_test = model.predict(x_test, num_iteration=model.best_iteration_)
    metrics = {
        "target": target_col,
        "rmse": rmse(y_test.to_numpy(), pred_test),
        "mae": mae(y_test.to_numpy(), pred_test),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "test_start": test_start,
        "test_end": test_end,
        "best_iteration": int(model.best_iteration_ or model.n_estimators),
    }

    booster = model.booster_
    importance = pd.DataFrame(
        {
            "feature": feature_cols,
            "importance_gain": booster.feature_importance(importance_type="gain"),
            "importance_split": booster.feature_importance(importance_type="split"),
        }
    ).sort_values("importance_gain", ascending=False)

    meta = {
        "target_key": target_key,
        "target_col": target_col,
        "feature_cols": feature_cols,
        "categorical_cols": categorical_cols,
        "metrics": metrics,
    }
    return model, meta, importance


def save_artifacts(
    model: lgb.LGBMRegressor,
    meta: dict[str, Any],
    importance: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    key = meta["target_key"]

    model_path = output_dir / f"{key}_model.joblib"
    meta_path = output_dir / f"{key}_metadata.json"
    imp_path = output_dir / f"{key}_feature_importance.csv"

    dump(model, model_path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    importance.to_csv(imp_path, index=False, encoding="utf-8-sig")


def main() -> None:
    args = parse_args()
    panel_paths = {
        "overseas": args.panel_overseas,
        "china": args.panel_china,
    }

    for target_key, panel_path in panel_paths.items():
        if not panel_path.exists():
            raise FileNotFoundError(panel_path)

        frame = read_csv_fallback(panel_path)
        model, meta, importance = fit_one(
            frame,
            target_key=target_key,
            test_start=args.test_start,
            test_end=args.test_end,
            seed=args.seed,
        )
        save_artifacts(model, meta, importance, args.model_dir)
        print(
            f"[{target_key}] RMSE={meta['metrics']['rmse']:.4f} "
            f"MAE={meta['metrics']['mae']:.4f} "
            f"best_iter={meta['metrics']['best_iteration']}"
        )


if __name__ == "__main__":
    main()
