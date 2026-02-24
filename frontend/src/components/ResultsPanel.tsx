import { RecommendationItem, SimulationScenario } from "@/features/analysis/types";

type Props = {
  simulations: SimulationScenario[];
  recommendations: RecommendationItem[];
};

function scenarioLabel(name: string): string {
  if (name === "optimistic") return "楽観シナリオ";
  if (name === "base") return "標準シナリオ";
  if (name === "pessimistic") return "悲観シナリオ";
  return name;
}

function riskLabel(level: string): string {
  if (level === "low") return "低";
  if (level === "medium") return "中";
  if (level === "high") return "高";
  return level;
}

function recommendationTypeLabel(type: string): string {
  if (type === "risk_leverage") return "依存活用プラン";
  if (type === "risk_diversification") return "依存分散プラン";
  return type;
}

export default function ResultsPanel({ simulations, recommendations }: Props) {
  return (
    <section className="results-grid">
      <div className="panel">
        <h2 className="panel-title">シナリオ別シミュレーション</h2>
        {simulations.length === 0 ? (
          <p className="muted">シミュレーション結果はまだありません。</p>
        ) : (
          <ul className="list">
            {simulations.map((scenario) => (
              <li key={scenario.name} className="list-item">
                <strong>{scenarioLabel(scenario.name)}</strong>
                <div>想定増減率: {scenario.expected_growth_rate}%</div>
                <div>リスク: {riskLabel(scenario.risk_level)}</div>
                <div>{scenario.note}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">戦略提案</h2>
        {recommendations.length === 0 ? (
          <p className="muted">提案データはまだありません。</p>
        ) : (
          <ul className="list">
            {recommendations.map((item) => (
              <li key={item.title} className="list-item">
                <strong>{item.title}</strong>
                <div className="pill">{recommendationTypeLabel(item.type)}</div>
                <div>{item.description}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
