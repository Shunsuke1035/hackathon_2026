import Link from "next/link";

export default function HomePage() {
  return (
    <main className="container">
      <h1 className="title">観光依存リスク分析アプリ（MVP）</h1>
      <p>FastAPI + Next.js + SQLite で構築した試作版です。</p>
      <p>
        <Link href="/login">ログイン画面へ</Link>
      </p>
      <p>
        <Link href="/signup">アカウント作成</Link>
      </p>
    </main>
  );
}
