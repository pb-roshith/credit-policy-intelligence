# Run the Credit Policy Intelligence Platform

Requires Node.js 18+, Python 3.10+, and PostgreSQL.

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
cd "C:\Users\2863775\Documents\credit policy intelligence\backend"
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

## Default administrator

The administrator login and PostgreSQL connection are configured in
`backend/.env`. The local development defaults are `admin` / `Admin@123456`,
with PostgreSQL at `postgresql://postgres:root@localhost:5432/credit_policy_intelligence`.
On first startup, the backend creates the database named in `DATABASE_URL` if it
does not exist. The configured PostgreSQL user must have permission to create
databases for that first run.
Change both passwords before deploying or sharing the application.
