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
