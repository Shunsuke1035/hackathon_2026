import { RecommendationItem, SimulationScenario } from "@/features/analysis/types";

type Props = {
  simulations: SimulationScenario[];
  recommendations: RecommendationItem[];
};

export default function ResultsPanel({ simulations, recommendations }: Props) {
  return (
    <section className="results-grid">
      <div className="panel">
        <h2 className="panel-title">Scenario Simulation</h2>
        {simulations.length === 0 ? (
          <p className="muted">No simulation data yet.</p>
        ) : (
          <ul className="list">
            {simulations.map((scenario) => (
              <li key={scenario.name} className="list-item">
                <strong>{scenario.name}</strong>
                <div>growth rate: {scenario.expected_growth_rate}%</div>
                <div>risk: {scenario.risk_level}</div>
                <div>{scenario.note}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">Strategic Recommendations</h2>
        {recommendations.length === 0 ? (
          <p className="muted">No recommendation data yet.</p>
        ) : (
          <ul className="list">
            {recommendations.map((item) => (
              <li key={item.title} className="list-item">
                <strong>{item.title}</strong>
                <div className="pill">{item.type}</div>
                <div>{item.description}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
