import { DependencyMetricsCurrent, DependencyMetricsSeriesPoint } from "@/features/analysis/types";

type Props = {
  marketLabel: string;
  current: DependencyMetricsCurrent | null;
  series: DependencyMetricsSeriesPoint[];
  loading: boolean;
  note?: string | null;
};

type ChartProps = {
  title: string;
  color: string;
  yMin: number;
  yMax: number;
  series: DependencyMetricsSeriesPoint[];
  accessor: (point: DependencyMetricsSeriesPoint) => number | null;
};

function formatFloat(value: number | null | undefined, digits = 3): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toLocaleString("ja-JP");
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function SimpleLineChart({ title, color, yMin, yMax, series, accessor }: ChartProps) {
  const width = 680;
  const height = 220;
  const padding = 24;
  const range = Math.max(yMax - yMin, 0.000001);

  const values = series.map((point) => accessor(point));
  const data = values
    .map((value, idx) => ({ idx, value }))
    .filter((item): item is { idx: number; value: number } => item.value != null && Number.isFinite(item.value));

  if (data.length < 2) {
    return (
      <div className="metric-chart-card">
        <div className="metric-chart-title">{title}</div>
        <p className="muted">時系列表示に必要なデータが不足しています。</p>
      </div>
    );
  }

  const xScale = (idx: number) =>
    padding + ((width - padding * 2) * idx) / Math.max(series.length - 1, 1);
  const yScale = (value: number) => {
    const clipped = Math.max(yMin, Math.min(yMax, value));
    return height - padding - ((height - padding * 2) * (clipped - yMin)) / range;
  };

  const polyline = data.map((item) => `${xScale(item.idx)},${yScale(item.value)}`).join(" ");
  const firstLabel = series[0]?.month_date ?? "";
  const lastLabel = series[series.length - 1]?.month_date ?? "";

  return (
    <div className="metric-chart-card">
      <div className="metric-chart-title">{title}</div>
      <svg className="metric-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <line x1={padding} x2={padding} y1={padding} y2={height - padding} stroke="#cbd5e1" strokeWidth="1" />
        <line
          x1={padding}
          x2={width - padding}
          y1={height - padding}
          y2={height - padding}
          stroke="#cbd5e1"
          strokeWidth="1"
        />
        <polyline fill="none" stroke={color} strokeWidth="2.5" points={polyline} />
      </svg>
      <div className="metric-chart-axis">
        <span>{firstLabel}</span>
        <span>{lastLabel}</span>
      </div>
    </div>
  );
}

export default function DependencyMetricsPanel({ marketLabel, current, series, loading, note }: Props) {
  return (
    <section className="panel">
      <h2 className="panel-title">依存度メトリクス（{marketLabel}）</h2>
      {note ? <p className="muted">{note}</p> : null}
      {loading ? (
        <p className="muted">メトリクスを読み込み中...</p>
      ) : current == null ? (
        <p className="muted">メトリクスデータはまだありません。</p>
      ) : (
        <>
          <div className="metric-meta">
            <span>
              対象: {current.year}年{current.month}月
            </span>
            <span>有効施設数: {formatInt(current.facility_count_active)} / {formatInt(current.facility_count_total)}</span>
          </div>
          <div className="metric-grid">
            <div className="metric-item">
              <div className="metric-label">市場集中度（施設分布HHI）</div>
              <div className="metric-value">{formatFloat(current.facility_hhi)}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">市場分散度（正規化エントロピー）</div>
              <div className="metric-value">{formatFloat(current.facility_entropy_norm_active)}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">外国市場構成HHI</div>
              <div className="metric-value">{formatFloat(current.foreign_hhi)}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">外国市場構成エントロピー（正規化）</div>
              <div className="metric-value">{formatFloat(current.foreign_entropy_norm)}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">選択市場のトップ施設シェア</div>
              <div className="metric-value">{formatPercent(current.facility_top1_share)}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">外国市場トップ国籍シェア</div>
              <div className="metric-value">
                {current.foreign_top1_market ?? "-"} / {formatPercent(current.foreign_top1_share)}
              </div>
            </div>
          </div>

          <div className="metric-charts">
            <SimpleLineChart
              title="市場集中度（HHI）時系列"
              color="#1d4ed8"
              yMin={0}
              yMax={1}
              series={series}
              accessor={(point) => point.facility_hhi}
            />
            <SimpleLineChart
              title="市場分散度（正規化エントロピー）時系列"
              color="#047857"
              yMin={0}
              yMax={1}
              series={series}
              accessor={(point) => point.facility_entropy_norm_active}
            />
          </div>
        </>
      )}
    </section>
  );
}
