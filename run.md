# Run the Credit Policy Intelligence Platform

Requires Node.js 18+ and Python 3.10+.

## 1. First-time setup and run

Open PowerShell in the project folder and start the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Open a second PowerShell window in the project folder and start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

## 2. Run after setup

Open PowerShell in the project folder and start the backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```

Open a second PowerShell window in the project folder and start the frontend:

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173**.

API documentation: **http://localhost:8000/docs**
