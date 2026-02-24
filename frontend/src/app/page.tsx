import Link from "next/link";

export default function HomePage() {
  return (
    <main className="container">
      <h1 className="title">Tourism Risk App (MVP)</h1>
      <p>FastAPI + Next.js + SQLite の最小構成です。</p>
      <p>
        <Link href="/login">ログイン画面へ</Link>
      </p>
    </main>
  );
}
