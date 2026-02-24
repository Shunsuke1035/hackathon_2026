# scripts

## build_profile_mart.py
Build normalized profile tables and an LLM-ready mart from raw tourism trend files.

Run:

```powershell
python scripts/build_profile_mart.py
```

Outputs:
- `data/processed/dim_country_profile_key.csv`
- `data/processed/fact_spending_profile.csv`
- `data/processed/fact_stay_profile.csv`
- `data/mart/mart_country_profile_for_llm.jsonl`

## build_dependency_metrics.py
Build dependency metrics from monthly hotel allocation CSV files.

Run:

```powershell
python scripts/build_dependency_metrics.py
```

Outputs:
- `data/processed/fact_dependency_metrics_facility_monthly.csv`
  - facility x month metrics (within-facility shares, HHI, entropy, top1)
- `data/processed/fact_dependency_metrics_region_monthly.csv`
  - ward(region) x month aggregated metrics
- `data/processed/fact_dependency_metrics_market_facility_monthly.csv`
  - market x month metrics across all facilities
  - includes facility-distribution entropy (your requested perspective)

## generate_hotel_heatmaps.py
Generate monthly folium heatmaps from hotel allocation CSV files.

Run (dependency ratio map, recommended):

```powershell
python scripts/generate_hotel_heatmaps.py --metric dependency
```

Run (raw count map):

```powershell
python scripts/generate_hotel_heatmaps.py --metric raw
```

Main options:
- `--input-dir` (default: `data/hotel_allocation_biased/hotel_allocation_biased`)
- `--output-dir` (default: `outputs/heatmaps`)
- `--transform` (`identity|sqrt|log1p`, default: `sqrt`)
- `--clip-quantile` (default: `0.99`)

Outputs:
- `outputs/heatmaps/heatmap_<source_file>_<segment>_<metric>.html`
- `outputs/heatmaps/heatmap_metric_summary_<metric>.csv`

## train_lightgbm_models.py
Train facility-level LightGBM models (overseas/china) from panel CSV files.

Run:

```powershell
python scripts/train_lightgbm_models.py
```

Main options:
- `--panel-overseas` (default: `data/hotel_allocation_biased/hotel_allocation_biased/panel_overseas_2025_with_features.csv`)
- `--panel-china` (default: `data/hotel_allocation_biased/hotel_allocation_biased/panel_chinease_2025_with_features.csv`)
- `--test-start` / `--test-end` (default: `2025-01-01` / `2025-06-01`)
- `--model-dir` (default: `models/lightgbm`)

Outputs:
- `models/lightgbm/overseas_model.joblib`
- `models/lightgbm/overseas_metadata.json`
- `models/lightgbm/overseas_feature_importance.csv`
- `models/lightgbm/china_model.joblib`
- `models/lightgbm/china_metadata.json`
- `models/lightgbm/china_feature_importance.csv`

## predict_lightgbm_scenarios.py
Run recursive monthly forecasts with trained LightGBM artifacts and scenario shocks.

Run:

```powershell
python scripts/predict_lightgbm_scenarios.py --event-id infectious_disease_resurgence --start-date 2026-01-01 --steps 3
```

Main options:
- `--model-dir` (default: `models/lightgbm`)
- `--exog-path` (default: `data/hotel_allocation_biased/hotel_allocation_biased/jnto_fx_merged_filled.csv`)
- `--scenario-path` (default: `data/hotel_allocation_biased/hotel_allocation_biased/scenario_event_shock_rates.csv`)
- `--fx-rate-change` (default: `0.10`)
- `--output-dir` (default: `outputs/forecasts`)

Outputs:
- `outputs/forecasts/forecast_<event_id>_<yyyymm>_steps<steps>.csv`
