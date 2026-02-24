import { ForecastResponse } from "@/features/analysis/types";

type Props = {
  forecast: ForecastResponse | null;
  loading: boolean;
  marketLabel: string;
};

const COLORS = ["#0f766e", "#1d4ed8", "#b91c1c", "#7c3aed", "#ea580c"];

function formatGuestCount(value: number): string {
  return `${Math.round(value).toLocaleString("ja-JP")}人`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function buildPath(values: number[], width: number, height: number, minY: number, maxY: number): string {
  if (values.length === 0) return "";
  const xStep = values.length === 1 ? 0 : width / (values.length - 1);
  const toY = (value: number) => {
    if (maxY === minY) return height / 2;
    const ratio = (value - minY) / (maxY - minY);
    return height - ratio * height;
  };

  return values
    .map((value, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${toY(value)}`)
    .join(" ");
}

export default function ForecastPanel({ forecast, loading, marketLabel }: Props) {
  if (loading) {
    return (
      <section className="panel">
        <h2 className="panel-title">LightGBM予測</h2>
        <p className="muted">予測データを読み込み中...</p>
      </section>
    );
  }

  if (!forecast || forecast.scenarios.length === 0) {
    return (
      <section className="panel">
        <h2 className="panel-title">LightGBM予測</h2>
        <p className="muted">予測データがありません。</p>
      </section>
    );
  }

  const xLabels = forecast.scenarios[0]?.points.map((point) => point.month_date) ?? [];
  const hasFacilityGuestCount = forecast.scenarios.some((scenario) =>
    scenario.points.some((point) => point.predicted_guest_count != null)
  );

  const chartUnitLabel = hasFacilityGuestCount ? "対象施設の予測人数" : "予測増減率";

  const series = forecast.scenarios.map((scenario) => ({
    id: scenario.scenario_id,
    name: scenario.scenario_name_ja,
    note: scenario.note,
    values: scenario.points.map((point) =>
      hasFacilityGuestCount
        ? (point.predicted_guest_count ?? point.predicted_guest_count_total ?? 0)
        : point.predicted_growth_rate
    ),
    points: scenario.points
  }));

  const allValues = series.flatMap((item) => item.values);
  const minY = Math.min(...allValues, 0);
  const maxY = Math.max(...allValues, 0);

  return (
    <section className="panel">
      <h2 className="panel-title">LightGBM予測</h2>
      <div className="metric-meta">
        <span>市場: {marketLabel}</span>
        <span>基準: {forecast.base_year}年{forecast.base_month}月</span>
        <span>モデル: {forecast.model_version}</span>
        <span>表示: {chartUnitLabel}</span>
      </div>

      <div className="metric-chart-card">
        <div className="metric-chart-title">{chartUnitLabel}（3か月）</div>
        <svg className="metric-chart-svg" viewBox="0 0 720 220" preserveAspectRatio="none">
          <line x1="0" y1="220" x2="720" y2="220" stroke="#cbd5e1" strokeWidth="1" />
          <line x1="0" y1="110" x2="720" y2="110" stroke="#e2e8f0" strokeWidth="1" />
          {series.map((item, index) => (
            <path
              key={item.id}
              d={buildPath(item.values, 720, 220, minY, maxY)}
              fill="none"
              stroke={COLORS[index % COLORS.length]}
              strokeWidth="2.5"
            />
          ))}
        </svg>
        <div className="metric-chart-axis">
          <span>{xLabels[0] ?? "-"}</span>
          <span>{xLabels[xLabels.length - 1] ?? "-"}</span>
        </div>
      </div>

      <ul className="list" style={{ marginTop: 12 }}>
        {series.map((item, index) => (
          <li key={item.id} className="list-item">
            <strong style={{ color: COLORS[index % COLORS.length] }}>{item.name}</strong>
            <div>{item.note}</div>
            <div>
              {item.points.map((point, valueIndex) => {
                const label = xLabels[valueIndex]?.slice(5, 7) ?? "-";
                const text =
                  hasFacilityGuestCount
                    ? formatGuestCount(point.predicted_guest_count ?? point.predicted_guest_count_total ?? 0)
                    : formatPercent(point.predicted_growth_rate);
                return (
                  <span key={`${item.id}-${valueIndex}`} style={{ marginRight: 8 }}>
                    {label}月: {text}
                  </span>
                );
              })}
            </div>
          </li>
        ))}
      </ul>
      {hasFacilityGuestCount ? null : (
        <p className="muted" style={{ marginTop: 8 }}>
          施設人数の算出条件が不足しているため、増減率表示にフォールバックしています。
        </p>
      )}
    </section>
  );
}
