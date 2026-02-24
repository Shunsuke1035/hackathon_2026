# Progress Log

最終更新: 2026-02-24

## 1. リリース済み（PR）
- #26 `feat: refine heatmap rendering and refresh dependency metrics/data path` (MERGED)
- #25 `feat: add dependency metrics pipeline (HHI and entropy)` (MERGED)
- #24 `chore(data): adopt reorganized allocation dataset and fix data paths` (MERGED)
- #23 `feat(facility): add authenticated facility profile CRUD API` (MERGED)
- #22 `feat(analysis): connect dependency map to real monthly dataset` (MERGED)
- #21 `chore(data): add hotel allocation dataset and align coordinate columns` (MERGED)
- #20 `feat(data): add profile ingest pipeline and normalized marts` (MERGED)
- #19 `docs(data): add source profile datasets and schema v1` (MERGED)
- #18 `feat(ui): 日本語UI表記へ統一` (MERGED)
- #17 `feat(frontend): issue #2 heatmap dashboard MVP` (MERGED)
- #16 `feat: bootstrap FastAPI + Next.js scaffold (SQLite auth)` (MERGED)

## 2. Issue状況（GitHub）
- Closed:
  - #1 要件定義（MVP）
  - #2 フロントMVP
  - #14（重複クローズ）
- Open:
  - #3 認証・施設情報・分析APIのMVP実装
  - #4 データ統合スキーマと前処理パイプライン
  - #5 宿泊者増減率回帰モデルとリスクシミュレーション
  - #6 国籍特性データを使った提案生成
  - #7 国籍依存度メトリクス基盤
  - #8 依存度×変動率の脆弱性スコア設計
  - #9 STLベース分解
  - #10 固定効果パネル回帰
  - #11 Monte Carloシミュレーション
  - #12 観光タイプクラスタリング
  - #13 ルールベース + LLM提案生成
  - #15 提案品質KPIとオフライン評価

## 3. 現在の実装ハイライト
- ヒートマップ:
  - 市場選択をクエリでAPIに渡して取得。
  - 初期ズームは要望に合わせて拡大調整済み。
- 依存度メトリクス:
  - 正規化HHI、Top10シェア、エントロピー系をAPI/UI連携。
  - 表示指標はUI要件に合わせて継続調整中。
- データ:
  - `data/hotel_allocation_biased/hotel_allocation_biased/` を正規パスとして運用。

## 4. 次の優先タスク案
1. #3 の残タスクを明確化してクローズ条件を定義
2. #4 のスキーマ固定と前処理の再現手順整備
3. #5 回帰モデルの最小実装（学習・評価・推論API）

## 2026-02-25 Update (Issue #5 related)
- Added reproducible model scripts:
  - `scripts/train_lightgbm_models.py`
  - `scripts/predict_lightgbm_scenarios.py`
- Added script docs:
  - `scripts/README.md`
- Updated backend startup guidance to avoid global Python runtime issues:
  - `README.md` now includes explicit `.venv`-based uvicorn command.
- Confirmed data changes in:
  - `data/hotel_allocation_biased/hotel_allocation_biased/panel_chinease_2025_with_features.csv`
  - `data/hotel_allocation_biased/hotel_allocation_biased/panel_overseas_2025_with_features.csv`
- Added LightGBM-backed forecast path in `backend/app/services/forecasting.py` with automatic fallback to skeleton when artifacts/dependencies are missing.
- Added forecast UI integration:
  - `frontend/src/features/analysis/api.ts` (`fetchForecast`)
  - `frontend/src/components/ForecastPanel.tsx`
  - `frontend/src/app/dashboard/page.tsx`
- Trained local model artifacts under `models/lightgbm/` and confirmed `/api/analysis/forecast` returns `model_version=lightgbm-v1`.
- Switched forecast default horizon to 3 months (kept configurable via request).
- Added in-memory TTL cache (5 minutes) for forecast payload generation in `backend/app/api/routes/analysis.py`.
