# hackathon_2026

観光需要の国籍依存リスクを可視化・分析するためのプロジェクトです。  
このリポジトリは次の2系統で構成します。

- `code/`: 既存の分析ノートブック（Python）
- `backend/`: FastAPI + SQLite のAPI
- `frontend/`: Next.js (TypeScript) の画面
- `data/`: ローカル管理データ（Git管理しない前提）

## Tech Stack

- Backend: FastAPI, SQLAlchemy, SQLite, JWT auth
- Frontend: Next.js (App Router, TypeScript)
- Analysis: pandas, scikit-learn, statsmodels, notebook

## 1) Analysis Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

## 2) Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

確認:
- `GET http://127.0.0.1:8000/api/health`
- `POST http://127.0.0.1:8000/api/auth/register`
- `POST http://127.0.0.1:8000/api/auth/login`

## 3) Frontend Setup

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

確認:
- `http://localhost:3000/`
- `http://localhost:3000/login`
- `http://localhost:3000/dashboard`

## Data Rules

- `data/` 配下はローカル保管
- 個票・機微情報は外部共有しない
- パスは絶対パス禁止、相対パスで扱う
