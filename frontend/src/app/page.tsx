import Link from "next/link";

export default function HomePage() {
  return (
    <main className="container">
      <h1 className="title">Tourism Risk App (MVP)</h1>
      <p>FastAPI + Next.js + SQLite scaffold.</p>
      <p>
        <Link href="/login">Go to login page</Link>
      </p>
    </main>
  );
}
