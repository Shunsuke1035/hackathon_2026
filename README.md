# hackathon_2026

Tourism demand risk analysis project.

## Repository Structure

- `code/`: notebook-based analysis
- `backend/`: FastAPI + SQLite API
- `frontend/`: Next.js (TypeScript) UI
- `data/`: local datasets (not committed)

## Tech Stack

- Backend: FastAPI, SQLAlchemy, SQLite, JWT
- Frontend: Next.js (App Router), React, Leaflet
- Analysis: pandas, scikit-learn, statsmodels

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

Core endpoints:

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/analysis/dependency?prefecture=kyoto&month=1`
- `GET /api/analysis/dependency-metrics?prefecture=kyoto&month=1&market=china`
- `POST /api/analysis/forecast`
- `POST /api/analysis/simulation`
- `POST /api/analysis/recommendation`

## 3) Frontend Setup

```powershell
cd frontend
cmd /c npm install
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
cmd /c npm run dev
```

Pages:

- `http://localhost:3000/`
- `http://localhost:3000/login`
- `http://localhost:3000/dashboard`

## Data Rules

- Keep raw datasets under `data/` locally
- Do not commit sensitive or contract-restricted data
- Use relative paths only (no absolute local paths)

## Project Docs

- Agent operation guide: `AGENTS.md`
- Progress tracker: `docs/progress.md`
