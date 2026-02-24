# scripts

## build_profile_mart.py

`data/` 配下の傾向データから、`processed` テーブルと LLM 用プロファイルを生成する。

実行:

```powershell
python scripts/build_profile_mart.py
```

出力:

- `data/processed/dim_country_profile_key.csv`
- `data/processed/fact_spending_profile.csv`
- `data/processed/fact_stay_profile.csv`
- `data/mart/mart_country_profile_for_llm.jsonl`
