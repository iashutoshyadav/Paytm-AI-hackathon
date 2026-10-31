# MerchantPulse AI

The AI teammate that spots Paytm merchants about to slip, talks to them in Hindi, fixes simple problems itself,
and brings in humans only when needed. Paytm Build for India AI Hackathon · Track 3.

## Demo day

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
```
Starts both servers (backend without auto-reload, frontend in production mode), checks the page really loads,
resets the demo and opens the browser. Script, fallbacks and judge Q&A: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).
Optional, once: `cd backend` → `.\.venv\Scripts\python.exe prewarm_voice.py` caches Hindi voice for fixed messages.

## First-time setup (after cloning)

Needs Python 3.11+ and Node 20+.
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then paste your Sarvam key into .env (never commit it)
cd ..\frontend
npm install
```
Without a Sarvam key everything still runs: the agent uses backup Hindi replies and voice is off.

## Run (development)

**Backend** (terminal 1)
```powershell
cd backend
.\.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

**Frontend** (terminal 2)
```powershell
cd frontend
npm run dev
```
Dashboard: http://localhost:3000

**Tests** (from `backend`, with the venv active): `python test_simulator.py`, `python test_engine.py`,
`python test_autonomy.py`, and `python test_sarvam.py` (needs the key).

## Layout
| Path | What |
|---|---|
| `backend/simulator.py` | 500 synthetic merchants × 30 days: payments, Soundbox health, settlements, planted problems and decoys |
| `backend/engine.py` | Detection and diagnosis against each merchant's own baseline, festival filter, Impact Score, ₹ at risk |
| `backend/autonomy.py` | Actions with risk levels, guardrails, playbooks, chat handling, recovery check, impact numbers |
| `backend/sarvam_client.py` | Sarvam chat (sarvam-105b-conversations), TTS (Bulbul v3), STT (Saaras v3) |
| `backend/stories.py` | The 5 planted problems + backup Hindi scripts |
| `backend/main.py` | FastAPI endpoints |
| `docs/API_CONTRACT.md` | JSON shapes both sides build against |
| `docs/DEMO_SCRIPT.md` | 4-minute demo, fallbacks, judge Q&A |
| `frontend/` | Next.js + Tailwind + Recharts dashboard |

## Stack
Next.js · TypeScript · Tailwind · Recharts · FastAPI · Pandas · SQLite · Sarvam AI (sarvam-105b, Saaras v3, Bulbul v3)
