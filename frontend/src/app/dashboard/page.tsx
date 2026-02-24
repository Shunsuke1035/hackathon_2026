"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import ResultsPanel from "@/components/ResultsPanel";
import { fetchDependencyPoints, fetchRecommendations, fetchSimulation } from "@/features/analysis/api";
import { MONTH_OPTIONS, PREFECTURES } from "@/features/analysis/constants";
import { FacilityInput, HeatPoint, RecommendationItem, SimulationScenario } from "@/features/analysis/types";
import { API_BASE_URL } from "@/lib/api";

const DependencyMap = dynamic(() => import("@/components/DependencyMap"), { ssr: false });

type MeResponse = {
  id: number;
  username: string;
  email: string;
};

export default function DashboardPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState("アカウント情報を読み込み中...");
  const [isError, setIsError] = useState(false);
  const [loadingMap, setLoadingMap] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);

  const [selectedPrefecture, setSelectedPrefecture] = useState("kyoto");
  const [selectedMonth, setSelectedMonth] = useState(1);

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
        setStatusMessage("準備完了です。都道府県と月を選択してください。");
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
        const points = await fetchDependencyPoints(selectedPrefecture, selectedMonth, token);
        setHeatPoints(points);
      } catch (error) {
        setIsError(true);
        setStatusMessage(error instanceof Error ? error.message : "地図データの取得に失敗しました。");
      } finally {
        setLoadingMap(false);
      }
    };
    loadDependencyMap();
  }, [selectedPrefecture, selectedMonth]);

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
    setStatusMessage("住所補助を適用しました（MVPの簡易推定）。");
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
              placeholder="例: 京都駅周辺"
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, address: event.target.value }))
              }
            />
          </label>
        </div>
        <div className="button-row">
          <button className="button secondary" onClick={handleAddressAssist} type="button">
            住所補助を適用
          </button>
          <button className="button" onClick={handleFacilityApply} type="button">
            施設ピンを更新
          </button>
          <button className="button" disabled={loadingInsights} onClick={handleLoadInsights} type="button">
            {loadingInsights ? "読み込み中..." : "提案とシミュレーションを取得"}
          </button>
        </div>
      </section>

      <section>
        <h2 className="panel-title">国籍依存度ヒートマップ</h2>
        {loadingMap ? (
          <div className="panel">
            <p className="muted">地図データを読み込み中...</p>
          </div>
        ) : (
          <DependencyMap
            center={selectedPrefectureData.center}
            facility={{ lat: facilityInput.lat, lng: facilityInput.lng }}
            points={heatPoints}
            zoom={selectedPrefectureData.zoom}
          />
        )}
      </section>

      <ResultsPanel recommendations={recommendations} simulations={simulations} />

      <p>
        <Link href="/login">ログイン画面へ戻る</Link>
      </p>
    </main>
  );
}
