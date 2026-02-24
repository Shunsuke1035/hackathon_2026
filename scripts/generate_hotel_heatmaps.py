#!/usr/bin/env python
"""Generate monthly hotel heatmaps from allocation CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (
    PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased",
    PROJECT_ROOT / "data" / "hotel_allocation_biased 1" / "hotel_allocation_biased",
)

TARGET_COLS_MASTER = [
    "中国",
    "韓国",
    "北米小計",
    "東南アジア小計",
    "ヨーロッパ小計",
    "海外合計",
    "国内合計",
]

LAT_CANDIDATES = ["latitude", "lat", "緯度"]
LON_CANDIDATES = ["longitude", "lon", "経度"]


def resolve_input_dir(custom: Path | None) -> Path:
    if custom is not None:
        return custom
    for candidate in INPUT_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No input directory found. Expected one of: "
        + ", ".join(str(path) for path in INPUT_DIR_CANDIDATES)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate folium heatmaps.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory with KCTA_*_hotel_allocation.csv files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/heatmaps"),
        help="Directory to write output HTML files",
    )
    parser.add_argument(
        "--metric",
        choices=["raw", "dependency"],
        default="dependency",
        help=(
            "raw: counts, dependency: percentage ratio. "
            "For foreign segments = segment / overseas_total * 100. "
            "For domestic/overseas total = value / (domestic+overseas) * 100."
        ),
    )
    parser.add_argument(
        "--transform",
        choices=["identity", "sqrt", "log1p"],
        default="sqrt",
        help="Weight transform before plotting.",
    )
    parser.add_argument(
        "--clip-quantile",
        type=float,
        default=0.99,
        help="Upper quantile clipping for weight (0-1].",
    )
    parser.add_argument("--zoom-start", type=int, default=12)
    parser.add_argument("--radius", type=int, default=16)
    parser.add_argument("--blur", type=int, default=20)
    parser.add_argument("--max-zoom", type=int, default=13)
    parser.add_argument("--tiles", default="CartoDB positron")
    parser.add_argument(
        "--columns",
        default=",".join(TARGET_COLS_MASTER),
        help="Comma-separated columns to render.",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=0,
        help="For testing only: limit number of processed files. 0 = all.",
    )
    return parser.parse_args()


def find_col(candidates: Iterable[str], columns: pd.Index) -> str | None:
    for col in candidates:
        if col in columns:
            return col
    return None


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def build_metric(frame: pd.DataFrame, column: str, mode: str) -> pd.Series:
    value = to_num(frame[column])
    if mode == "raw":
        return value

    overseas = to_num(frame["海外合計"]) if "海外合計" in frame.columns else pd.Series(0, index=frame.index)
    domestic = to_num(frame["国内合計"]) if "国内合計" in frame.columns else pd.Series(0, index=frame.index)

    if column in ("海外合計", "国内合計"):
        denom = (overseas + domestic).replace(0, np.nan)
    else:
        denom = overseas.replace(0, np.nan)

    ratio = (value / denom).replace([np.inf, -np.inf], np.nan).fillna(0)
    return ratio * 100.0


def apply_transform(series: pd.Series, name: str) -> pd.Series:
    s = series.clip(lower=0)
    if name == "identity":
        return s
    if name == "log1p":
        return np.log1p(s)
    return np.sqrt(s)


def map_center(frame: pd.DataFrame, lat_col: str, lon_col: str) -> list[float]:
    return [float(frame[lat_col].median()), float(frame[lon_col].median())]


def main() -> None:
    args = parse_args()
    input_dir = resolve_input_dir(args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    target_cols_master = [c.strip() for c in args.columns.split(",") if c.strip()]
    files = sorted(input_dir.glob("KCTA_*_hotel_allocation.csv"))
    if args.limit_files > 0:
        files = files[: args.limit_files]

    if not files:
        raise FileNotFoundError(f"No target CSV files found in: {input_dir}")

    summary_records: list[dict[str, object]] = []

    for path in files:
        df = read_csv_with_fallback(path)

        lat_col = find_col(LAT_CANDIDATES, df.columns)
        lon_col = find_col(LON_CANDIDATES, df.columns)
        if lat_col is None or lon_col is None:
            print(f"skip(no-lat-lon): {path.name}")
            continue

        target_cols = [c for c in target_cols_master if c in df.columns]
        if not target_cols:
            print(f"skip(no-target-cols): {path.name}")
            continue

        required_cols = list(dict.fromkeys([lat_col, lon_col, *target_cols, "海外合計", "国内合計"]))
        required_cols = [c for c in required_cols if c in df.columns]
        base = df[required_cols].copy()
        base[lat_col] = pd.to_numeric(base[lat_col], errors="coerce")
        base[lon_col] = pd.to_numeric(base[lon_col], errors="coerce")
        base = base.dropna(subset=[lat_col, lon_col])
        if base.empty:
            print(f"skip(no-valid-rows): {path.name}")
            continue

        center = map_center(base, lat_col, lon_col)
        basename = path.stem

        for col in target_cols:
            metric = build_metric(base, col, args.metric)
            plot_df = pd.DataFrame(
                {
                    "lat": base[lat_col],
                    "lon": base[lon_col],
                    "metric": metric,
                }
            )
            plot_df = plot_df[plot_df["metric"] > 0].copy()
            if plot_df.empty:
                continue

            weights = apply_transform(plot_df["metric"], args.transform)
            if 0 < args.clip_quantile < 1:
                cap = float(weights.quantile(args.clip_quantile))
                weights = weights.clip(upper=cap)
            plot_df["weight"] = weights

            m = folium.Map(
                location=center,
                zoom_start=args.zoom_start,
                tiles=args.tiles,
                control_scale=True,
            )
            HeatMap(
                plot_df[["lat", "lon", "weight"]].values.tolist(),
                radius=args.radius,
                blur=args.blur,
                max_zoom=args.max_zoom,
                min_opacity=0.25,
                gradient={
                    0.2: "#2C7BB6",
                    0.4: "#00A6CA",
                    0.6: "#F9D057",
                    0.8: "#F29E2E",
                    1.0: "#D7191C",
                },
            ).add_to(m)

            out_html = args.output_dir / f"heatmap_{basename}_{col}_{args.metric}.html"
            m.save(out_html.as_posix())

            summary_records.append(
                {
                    "file": path.name,
                    "segment": col,
                    "metric_mode": args.metric,
                    "rows_plotted": int(len(plot_df)),
                    "metric_min": float(plot_df["metric"].min()),
                    "metric_mean": float(plot_df["metric"].mean()),
                    "metric_p95": float(plot_df["metric"].quantile(0.95)),
                    "metric_max": float(plot_df["metric"].max()),
                }
            )

        print(f"done: {basename}")

    if summary_records:
        summary = pd.DataFrame(summary_records)
        out_csv = args.output_dir / f"heatmap_metric_summary_{args.metric}.csv"
        summary.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"summary: {out_csv}")

    print("done: generated heatmaps.")


if __name__ == "__main__":
    main()
