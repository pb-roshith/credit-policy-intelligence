# Start the applications

The shared AI provider lives in `cd_cpi_server/ai_runtime.py`, with its tests
in `cd_cpi_server/tests`. CPI and Dossier both load this shared implementation.
Run its tests from `cd_cpi_server` using the Dossier Python environment:
`credit_dossier_backend/.venv/Scripts/python.exe -m unittest discover -s tests`.

AI generation supports `AI_PROVIDER=gemini` or `AI_PROVIDER=mistral`. Set the
same provider in the CPI backend, Dossier backend, and Dossier MCP `.env` files.
Gemini uses `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.5-flash-lite` through
the official `google-genai` Python SDK. Install each service's requirements
after updating, then restart all three Python services. `.env.example` contains
placeholders; keep real keys in the ignored `.env` files.

Temporary Gemini capacity failures (including HTTP 503) use the SDK's bounded
retry policy: six total attempts, with exponential backoff starting at two
seconds and capped at sixteen seconds, plus jitter. Each Python server process
allows at most two simultaneous Gemini requests, including retries. Persistent
provider overload still requires trying again later; the configured model is
preserved.

Gemini agent definitions, conversations, and source documents are stored in
the ignored `.ai-data/gemini.sqlite3` file at the repository root. Both backends
and MCP must share this file; `GEMINI_STORE_PATH` can override its location.
Back it up with the application data. Gemini receives the attached documents
as context; it does not use Mistral's hosted retrieval or Observability judges.
CPI restores its policy library from local PDFs on first use. For Dossier,
re-manufacture the company data pack and re-sync existing deals after switching
providers; re-upload documents stored only in the previous provider. Keep the
original Mistral key configured if you plan to switch back later.

Start PostgreSQL, then double-click `start_all.bat` in this folder. It opens
one Windows Terminal window with seven named Command Prompt tabs using the existing
Python environments and Node dependencies. Windows Terminal is required.
Keep the tabs open while using the applications. Double-click `stop_all.bat` to
stop all seven servers together, or press Ctrl+C in a tab to stop one server.
The self-contained `stop_all.bat` identifies this project's processes
on the seven server ports and stop their child processes too. Server tabs remain
open and can be closed afterward. PostgreSQL stays running.
If a port is already occupied, stop its existing server before starting again.

| Server | Port |
| --- | --- |
| Credit Dossier MCP | 8004 |
| Credit Dossier backend | 8003 |
| Credit Dossier frontend | 8081 |
| Credit Policy Intelligence backend | 8002 |
| Credit Policy Intelligence frontend | 5173 |
| Data Manufacturing backend | 8005 |
| Data Manufacturing frontend | 5174 |

Open Credit Dossier at http://localhost:8081 and Credit Policy Intelligence at
http://localhost:5173 after their terminals report that startup is complete.

First-time setup and individual startup instructions are in
[cd_cpi_server/run.md](cd_cpi_server/run.md) and [cpi_server/run.md](cpi_server/run.md).
Shared frontend components are stored in `cd_cpi_server/credit_dossier_backend/shared`.
Credit analysts see deals from all relationship managers in both applications.
Relationship managers see their own deals.

Data Manufacturing is now a separate application at http://localhost:5174. The CPI application retains its other pages. Setup and individual startup instructions: [dm_server/run.md](dm_server/run.md). DM shares account credentials and generated data with CPI, with independent login sessions.
