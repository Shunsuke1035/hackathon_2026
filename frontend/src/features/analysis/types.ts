export type PrefectureOption = {
  code: string;
  name: string;
  center: { lat: number; lng: number };
  zoom: number;
};

export type HeatPoint = {
  lat: number;
  lng: number;
  dependency_score: number;
  market_count?: number | null;
  market: string;
};

export type DependencyMarketKey =
  | "china"
  | "korea"
  | "north_america"
  | "southeast_asia"
  | "europe"
  | "japan";

export type DependencyMetricsSeriesPoint = {
  year: number;
  month: number;
  month_date: string;
  market_total: number;
  facility_count_total: number;
  facility_count_active: number;
  facility_hhi: number | null;
  facility_hhi_norm_active: number | null;
  facility_entropy: number | null;
  facility_entropy_norm_active: number | null;
  facility_top1_share: number | null;
  facility_top10_share: number | null;
  foreign_hhi: number | null;
  foreign_entropy: number | null;
  foreign_entropy_norm: number | null;
  all_hhi: number | null;
  all_entropy: number | null;
  all_entropy_norm: number | null;
};

export type DependencyMetricsCurrent = {
  year: number;
  month: number;
  month_date: string;
  selected_market: DependencyMarketKey;
  market_total: number;
  facility_count_total: number;
  facility_count_active: number;
  facility_hhi: number | null;
  facility_hhi_norm_active: number | null;
  facility_entropy: number | null;
  facility_entropy_norm_active: number | null;
  facility_top1_share: number | null;
  facility_top10_share: number | null;
  foreign_hhi: number | null;
  foreign_entropy: number | null;
  foreign_entropy_norm: number | null;
  foreign_top1_market: string | null;
  foreign_top1_share: number | null;
  all_hhi: number | null;
  all_entropy: number | null;
  all_entropy_norm: number | null;
  all_top1_market: string | null;
  all_top1_share: number | null;
};

export type DependencyMetricsResponse = {
  prefecture: string;
  month: number;
  year: number;
  market: DependencyMarketKey;
  current: DependencyMetricsCurrent;
  series: DependencyMetricsSeriesPoint[];
  note?: string | null;
};

export type FacilityInput = {
  lat: number;
  lng: number;
  address?: string;
};

export type SimulationScenario = {
  name: string;
  expected_growth_rate: number;
  risk_level: string;
  note: string;
};

export type RecommendationItem = {
  type: string;
  title: string;
  description: string;
};

export type ForecastPoint = {
  step: number;
  year: number;
  month: number;
  month_date: string;
  predicted_growth_rate: number;
  applied_shock_rate: number;
  seasonal_component: number;
};

export type ForecastScenario = {
  scenario_id: string;
  scenario_name_ja: string;
  note: string;
  points: ForecastPoint[];
};

export type ForecastScenarioMeta = {
  event_id: string;
  event_name_ja: string;
  note: string;
};

export type ForecastResponse = {
  model_version: string;
  target_metric: string;
  prefecture: string;
  market: DependencyMarketKey;
  base_year: number;
  base_month: number;
  horizon_months: number;
  baseline_growth_rate: number;
  feature_snapshot: Record<string, number>;
  available_scenarios: ForecastScenarioMeta[];
  scenarios: ForecastScenario[];
};
