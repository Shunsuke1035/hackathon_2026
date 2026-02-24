"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { API_BASE_URL } from "@/lib/api";

type MeResponse = {
  id: number;
  username: string;
  email: string;
};

export default function DashboardPage() {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState("読み込み中...");
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      setIsError(true);
      setMessage("未ログインです。ログイン画面へ移動してください。");
      return;
    }

    const fetchUser = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        });
        if (!response.ok) {
          throw new Error("認証に失敗しました。再ログインしてください。");
        }
        const data = (await response.json()) as MeResponse;
        setUser(data);
        setMessage("ログイン状態を確認できました。");
      } catch (error) {
        setIsError(true);
        setMessage(error instanceof Error ? error.message : "Unknown error");
      }
    };
    fetchUser();
  }, []);

  return (
    <main className="container">
      <h1 className="title">ダッシュボード（雛形）</h1>
      <p className={`message ${isError ? "error" : "ok"}`}>{message}</p>
      {user ? (
        <div>
          <p>user_id: {user.id}</p>
          <p>username: {user.username}</p>
          <p>email: {user.email}</p>
        </div>
      ) : null}
      <p>
        <Link href="/login">ログイン画面へ戻る</Link>
      </p>
    </main>
  );
}
