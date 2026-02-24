"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import DependencyMetricsPanel from "@/components/DependencyMetricsPanel";
import ResultsPanel from "@/components/ResultsPanel";
import { fetchDependencyMetrics, fetchDependencyPoints, fetchRecommendations, fetchSimulation } from "@/features/analysis/api";
import { MONTH_OPTIONS, PREFECTURES } from "@/features/analysis/constants";
import {
  DependencyMarketKey,
  DependencyMetricsResponse,
  FacilityInput,
  HeatPoint,
  RecommendationItem,
  SimulationScenario
} from "@/features/analysis/types";
import { API_BASE_URL } from "@/lib/api";

const DependencyMap = dynamic(() => import("@/components/DependencyMap"), { ssr: false });

type MeResponse = {
  id: number;
  username: string;
  email: string;
};

type MarketOption = {
  value: DependencyMarketKey | "all";
  label: string;
};

const MARKET_OPTIONS: MarketOption[] = [
  { value: "all", label: "すべて" },
  { value: "china", label: "中国" },
  { value: "korea", label: "韓国" },
  { value: "north_america", label: "北米" },
  { value: "southeast_asia", label: "東南アジア" },
  { value: "europe", label: "ヨーロッパ" },
  { value: "japan", label: "国内" }
];

export default function DashboardPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState("アカウント情報を読み込み中...");
  const [isError, setIsError] = useState(false);
  const [loadingMap, setLoadingMap] = useState(false);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);

  const [selectedPrefecture, setSelectedPrefecture] = useState("kyoto");
  const [selectedMonth, setSelectedMonth] = useState(1);
  const [selectedYear, setSelectedYear] = useState<number | "latest">("latest");
  const [selectedMarket, setSelectedMarket] = useState<MarketOption["value"]>("china");

  const selectedPrefectureData = useMemo(
    () => PREFECTURES.find((prefecture) => prefecture.code === selectedPrefecture) ?? PREFECTURES[0],
    [selectedPrefecture]
  );

  const [facilityInput, setFacilityInput] = useState<FacilityInput>({
    lat: selectedPrefectureData.center.lat,
    lng: selectedPrefectureData.center.lng,
    address: ""
  });
  const [heatPoints, setHeatPoints] = useState<HeatPoint[]>([]);
  const [simulations, setSimulations] = useState<SimulationScenario[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [dependencyMetrics, setDependencyMetrics] = useState<DependencyMetricsResponse | null>(null);
  const [metricsNote, setMetricsNote] = useState<string | null>(null);

  const displayedHeatPoints = heatPoints;

  const metricsMarket = useMemo<DependencyMarketKey>(
    () => (selectedMarket === "all" ? "china" : selectedMarket),
    [selectedMarket]
  );

  const metricsPanelNote = useMemo(() => {
    const fallbackNote =
      selectedMarket === "all" ? "市場が「すべて」の場合、メトリクスは「中国」を基準表示します。" : null;
    if (fallbackNote && metricsNote) {
      return `${fallbackNote} / ${metricsNote}`;
    }
    return fallbackNote ?? metricsNote;
  }, [selectedMarket, metricsNote]);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      setIsError(true);
      setStatusMessage("未ログインです。先にログインしてください。");
      return;
    }

    const fetchCurrentUser = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("認証に失敗しました。");
        const data = (await response.json()) as MeResponse;
        setCurrentUser(data);
        setStatusMessage("ログイン済みです。地域と月を選択してください。");
        setIsError(false);
      } catch (error) {
        setIsError(true);
        setStatusMessage(error instanceof Error ? error.message : "不明なエラーが発生しました。");
      }
    };
    fetchCurrentUser();
  }, []);

  useEffect(() => {
    setFacilityInput((previous) => ({
      ...previous,
      lat: selectedPrefectureData.center.lat,
      lng: selectedPrefectureData.center.lng
    }));
  }, [selectedPrefectureData.center.lat, selectedPrefectureData.center.lng]);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) return;

    const loadDependencyMap = async () => {
      setLoadingMap(true);
      setIsError(false);
      try {
        const payload = await fetchDependencyPoints(
          selectedPrefecture,
          selectedMonth,
          token,
          selectedMarket,
          selectedYear === "latest" ? undefined : selectedYear
        );
        setHeatPoints(payload.points);

        const suffix = payload.note ? ` / ${payload.note}` : "";
        setStatusMessage(
          `ヒートマップ更新: ${payload.year}年${selectedMonth}月, ${payload.points.length}点${suffix}`
        );
      } catch (error) {
        setIsError(true);
        setStatusMessage(error instanceof Error ? error.message : "地図データの取得に失敗しました。");
      } finally {
        setLoadingMap(false);
      }
    };
    loadDependencyMap();
  }, [selectedPrefecture, selectedMonth, selectedYear, selectedMarket]);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) return;

    const loadMetrics = async () => {
      setLoadingMetrics(true);
      try {
        const payload = await fetchDependencyMetrics(
          selectedPrefecture,
          selectedMonth,
          metricsMarket,
          token,
          selectedYear === "latest" ? undefined : selectedYear
        );
        setDependencyMetrics(payload);
        setMetricsNote(payload.note ?? null);
      } catch (error) {
        setMetricsNote(error instanceof Error ? error.message : "依存度メトリクスの取得に失敗しました。");
      } finally {
        setLoadingMetrics(false);
      }
    };
    loadMetrics();
  }, [selectedPrefecture, selectedMonth, selectedYear, metricsMarket]);

  const handleFacilityApply = () => {
    if (Number.isNaN(facilityInput.lat) || Number.isNaN(facilityInput.lng)) {
      setIsError(true);
      setStatusMessage("緯度・経度は数値で入力してください。");
      return;
    }
    setIsError(false);
    setStatusMessage("施設位置を更新しました。");
  };

  const handleAddressAssist = () => {
    const addressText = facilityInput.address ?? "";
    const hash = Array.from(addressText).reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const latOffset = ((hash % 13) - 6) * 0.003;
    const lngOffset = ((hash % 17) - 8) * 0.003;
    setFacilityInput((previous) => ({
      ...previous,
      lat: Number((selectedPrefectureData.center.lat + latOffset).toFixed(6)),
      lng: Number((selectedPrefectureData.center.lng + lngOffset).toFixed(6))
    }));
    setIsError(false);
    setStatusMessage("住所から位置補助を反映しました（簡易推定）。");
  };

  const handleLoadInsights = async () => {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      setIsError(true);
      setStatusMessage("ログイントークンが見つかりません。再ログインしてください。");
      return;
    }
    setLoadingInsights(true);
    setIsError(false);
    try {
      const [simData, recommendationData] = await Promise.all([
        fetchSimulation(selectedPrefecture, selectedMonth, facilityInput, token),
        fetchRecommendations(selectedPrefecture, selectedMonth, facilityInput, token)
      ]);
      setSimulations(simData);
      setRecommendations(recommendationData);
      setStatusMessage("シミュレーションと提案の読み込みが完了しました。");
    } catch (error) {
      setIsError(true);
      setStatusMessage(error instanceof Error ? error.message : "分析結果の取得に失敗しました。");
    } finally {
      setLoadingInsights(false);
    }
  };

  return (
    <main className="container wide">
      <h1 className="title">国籍依存度ダッシュボード</h1>
      <p className={`message ${isError ? "error" : "ok"}`}>{statusMessage}</p>

      {currentUser ? (
        <div className="panel">
          <div className="panel-title">ユーザー情報</div>
          <div className="meta-row">
            <span>ID: {currentUser.id}</span>
            <span>ユーザー名: {currentUser.username}</span>
            <span>メール: {currentUser.email}</span>
          </div>
        </div>
      ) : null}

      <section className="panel">
        <h2 className="panel-title">表示条件</h2>
        <div className="controls-grid">
          <label>
            都道府県
            <select
              className="input"
              value={selectedPrefecture}
              onChange={(event) => setSelectedPrefecture(event.target.value)}
            >
              {PREFECTURES.map((prefecture) => (
                <option key={prefecture.code} value={prefecture.code}>
                  {prefecture.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            年
            <select
              className="input"
              value={selectedYear}
              onChange={(event) => {
                const next = event.target.value;
                setSelectedYear(next === "latest" ? "latest" : Number(next));
              }}
            >
              <option value="latest">最新</option>
              <option value="2025">2025</option>
              <option value="2024">2024</option>
            </select>
          </label>

          <label>
            月
            <select
              className="input"
              value={selectedMonth}
              onChange={(event) => setSelectedMonth(Number(event.target.value))}
            >
              {MONTH_OPTIONS.map((month) => (
                <option key={month.value} value={month.value}>
                  {month.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            市場
            <select
              className="input"
              value={selectedMarket}
              onChange={(event) => setSelectedMarket(event.target.value as MarketOption["value"])}
            >
              {MARKET_OPTIONS.map((market) => (
                <option key={market.value} value={market.value}>
                  {market.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">施設位置入力</h2>
        <div className="controls-grid">
          <label>
            緯度
            <input
              className="input"
              type="number"
              step="0.000001"
              value={facilityInput.lat}
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, lat: Number(event.target.value) }))
              }
            />
          </label>
          <label>
            経度
            <input
              className="input"
              type="number"
              step="0.000001"
              value={facilityInput.lng}
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, lng: Number(event.target.value) }))
              }
            />
          </label>
          <label className="full-width">
            住所（任意）
            <input
              className="input"
              value={facilityInput.address ?? ""}
              placeholder="例: 京都市下京区"
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, address: event.target.value }))
              }
            />
          </label>
        </div>
        <div className="button-row">
          <button className="button secondary" onClick={handleAddressAssist} type="button">
            住所から位置補助
          </button>
          <button className="button" onClick={handleFacilityApply} type="button">
            施設位置を反映
          </button>
          <button className="button" disabled={loadingInsights} onClick={handleLoadInsights} type="button">
            {loadingInsights ? "読み込み中..." : "提案とシミュレーションを取得"}
          </button>
        </div>
      </section>

      <section>
        <h2 className="panel-title">国籍依存度ヒートマップ</h2>
        <p className="muted">表示市場: {MARKET_OPTIONS.find((m) => m.value === selectedMarket)?.label ?? "-"}（{displayedHeatPoints.length} 点）</p>
        {loadingMap ? (
          <div className="panel">
            <p className="muted">地図データを読み込み中...</p>
          </div>
        ) : (
          <DependencyMap
            center={selectedPrefectureData.center}
            facility={{ lat: facilityInput.lat, lng: facilityInput.lng }}
            points={displayedHeatPoints}
            zoom={selectedPrefectureData.zoom}
          />
        )}
      </section>

      <DependencyMetricsPanel
        current={dependencyMetrics?.current ?? null}
        series={dependencyMetrics?.series ?? []}
        loading={loadingMetrics}
        marketLabel={MARKET_OPTIONS.find((m) => m.value === metricsMarket)?.label ?? "中国"}
        note={metricsPanelNote}
      />

      <ResultsPanel recommendations={recommendations} simulations={simulations} />

      <p>
        <Link href="/login">ログイン画面へ戻る</Link>
      </p>
    </main>
  );
}
