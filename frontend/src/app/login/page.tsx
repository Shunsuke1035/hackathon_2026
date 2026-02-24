"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { API_BASE_URL } from "@/lib/api";

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username: string;
    email: string;
  };
};

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [isError, setIsError] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    setIsError(false);

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Login failed");
      }

      const data = (await response.json()) as LoginResponse;
      window.localStorage.setItem("access_token", data.access_token);
      window.localStorage.setItem("current_user", JSON.stringify(data.user));
      setMessage("Login successful. Redirecting to dashboard...");
      router.push("/dashboard");
    } catch (error) {
      setIsError(true);
      setMessage(error instanceof Error ? error.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <h1 className="title">Login</h1>
      <form className="form" onSubmit={onSubmit}>
        <input
          className="input"
          placeholder="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
        <input
          className="input"
          type="password"
          placeholder="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <button className="button" disabled={loading} type="submit">
          {loading ? "Logging in..." : "Login"}
        </button>
      </form>
      {message ? <p className={`message ${isError ? "error" : "ok"}`}>{message}</p> : null}
    </main>
  );
}
