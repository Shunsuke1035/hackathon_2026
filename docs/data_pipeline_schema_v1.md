# Data Pipeline Schema v1 (Issue #4 / #6 / #13 / #15)

## 目的

提案生成で「毎回生CSVをLLMへ投入」する運用を避け、以下を満たす。

- `#4`: 再現可能な前処理と統一スキーマ
- `#6` `#13`: 根拠付き提案生成のための整形コンテキスト
- `#15`: 提案評価の再計算性

結論: **ハイブリッド方式**  
`raw CSV -> 正規化テーブル -> LLM用プロファイルJSON/短文` を採用する。

## データレイヤ

### 1. Raw (`data/raw` 想定)

- `KCTA.csv`
- `jnto_fx_merged.csv`
- `2022_Tourism_Spending_Trends_by_Nationality.csv`
- `2022_Tourism_Spending_Trends_by_Japan.csv`
- `2022_Tourism_Stay_Trends_by_Nationality.csv`
- `2022_Tourism_Stay_Trends_by_Japan.csv`

備考:
- 日本向けデータは別ファイル扱いを維持する
- rawは変更せず、processedで整合を取る

### 2. Processed (`data/processed` 想定)

#### `dim_country_profile_key.parquet`

- `country_profile_key` (string, PK)
  - 例: `china`, `north_america`, `korea`, `europe`, `southeast_asia`, `japan`
- `country_label_ja` (string)
- `source_group` (string)
  - `nationality` or `japan_special`
- `is_active` (bool)

#### `fact_tourism_panel_monthly.parquet`

`#4` の主テーブル（都道府県x月のパネル）

- `month_date` (date, PK part)
- `prefecture_code` (string, PK part)
- `hotel_id` (string, nullable, PK part)
- `visitors_total` (float)
- `yoy_rate` (float, nullable)
- `yoy_diff` (float, nullable)
- `usd_jpy` (float, nullable)
- `cny_jpy` (float, nullable)
- `visitors_china` (float, nullable)
- `visitors_north_america` (float, nullable)
- `visitors_korea` (float, nullable)
- `visitors_europe` (float, nullable)
- `visitors_southeast_asia` (float, nullable)
- `visitors_japan` (float, nullable)
- `dep_top1_share` (float)
- `dep_hhi` (float)
- `dep_entropy` (float)

#### `fact_spending_profile.parquet`

国籍別/日本別の消費傾向を縦持ちに統合

- `country_profile_key` (string, FK)
- `profile_scope` (string)
  - `nationality` or `japan_special`
- `metric_category` (string)
  - 例: `宿泊費`, `飲食費`, `交通費`
- `metric_name` (string)
  - 例: `purchase_rate`, `spender_unit_price`
- `metric_value` (float)
- `unit` (string)
  - `%`, `JPY_PER_PERSON`
- `source_year` (int)
- `source_file` (string)

#### `fact_stay_profile.parquet`

滞在期間傾向を縦持ちに統合

- `country_profile_key` (string, FK)
- `profile_scope` (string)
- `stay_bin` (string)
  - 例: `3日以内`, `4-6日`, `7-13日`
- `traveler_count` (float, nullable)
- `unit_spend_jpy` (float, nullable)
- `source_year` (int)
- `source_file` (string)

### 3. LLM Context (`data/mart` 想定)

#### `mart_country_profile_for_llm.jsonl`

1行1国籍キーの要約コンテキスト。提案APIはこれを優先参照。

- `country_profile_key` (string)
- `summary_ja` (string)
- `evidence` (object)
  - `top_spending_categories` (array)
  - `stay_distribution` (array)
  - `data_points` (array of `{field, value, unit, source}`)
- `profile_version` (string)
- `generated_at` (datetime)

## 推奨パイプライン手順

1. `raw` 取込
2. ヘッダ行正規化
   - 日本語多段ヘッダをフラット化
3. キー統一
   - `country_profile_key` へ集約
4. 指標整形
   - `%`/`円` を数値列へ
5. `processed` 出力
6. LLM用要約生成（ルール+テンプレ）
7. `mart` 出力

## 提案生成時の参照方針

### NG
- 毎回 raw CSV 全量をGemini/OpenAIへ投入

### OK
- `processed` から必要行のみ抽出
- `mart_country_profile_for_llm` をプロンプトへ投入
- 追加で `fact_tourism_panel_monthly` の当該地域・月の数値を添付

## 推奨コンテキスト仕様（提案API入力）

```json
{
  "prefecture_code": "kyoto",
  "month_date": "2022-10-01",
  "facility": { "lat": 35.0, "lng": 135.7 },
  "dependency_metrics": {
    "top1_share": 0.42,
    "hhi": 0.28,
    "entropy": 1.36
  },
  "country_profiles": [
    {
      "country_profile_key": "china",
      "summary_ja": "高単価カテゴリの寄与が高い一方で短期集中の傾向がある。",
      "evidence": {
        "top_spending_categories": ["宿泊費", "買物代"],
        "stay_distribution": ["4-6日", "7-13日"]
      }
    }
  ]
}
```

## データ品質チェック（最低限）

- キー一意性
  - `fact_tourism_panel_monthly`: `month_date + prefecture_code + hotel_id`
- 範囲チェック
  - `dep_hhi`: `[0, 1]`
  - `dep_entropy`: `[0, log(N)]`
  - `purchase_rate`: `[0, 100]`
- 欠損チェック
  - `country_profile_key` 欠損禁止
- ソース追跡
  - すべてに `source_file`, `source_year` 付与

## 実装順（Issue対応）

1. `#4 PR1`: スキーマ定義と列マッピング辞書
2. `#4 PR2`: raw取込・多段ヘッダ正規化
3. `#4 PR3`: panel/profile出力
4. `#6/#13`: context-builderで`mart`参照
5. `#15`: 提案評価で`profile_version`単位比較
