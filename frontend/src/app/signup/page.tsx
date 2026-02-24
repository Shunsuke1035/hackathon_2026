"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { API_BASE_URL } from "@/lib/api";

type RegisterError = {
  detail?: string;
};

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setIsError(false);
    setMessage("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password })
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as RegisterError;
        throw new Error(payload.detail ?? "サインアップに失敗しました");
      }

      setMessage("アカウント作成に成功しました。ログイン画面へ移動します。");
      setTimeout(() => router.push("/login"), 800);
    } catch (error) {
      setIsError(true);
      setMessage(error instanceof Error ? error.message : "サインアップに失敗しました");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <h1 className="title">新規登録</h1>
      <form className="form" onSubmit={onSubmit}>
        <input
          className="input"
          placeholder="ユーザー名"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          minLength={3}
          maxLength={64}
          required
        />
        <input
          className="input"
          type="email"
          placeholder="メールアドレス"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <input
          className="input"
          type="password"
          placeholder="パスワード（8文字以上）"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          minLength={8}
          maxLength={128}
          required
        />
        <button className="button" disabled={loading} type="submit">
          {loading ? "作成中..." : "アカウント作成"}
        </button>
      </form>
      {message ? <p className={`message ${isError ? "error" : "ok"}`}>{message}</p> : null}
      <p className="message">
        すでにアカウントをお持ちですか？ <Link href="/login">ログインへ</Link>
      </p>
    </main>
  );
}
