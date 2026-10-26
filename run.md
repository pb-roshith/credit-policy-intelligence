# Start both applications

Start PostgreSQL, then double-click `start_all.bat` in this folder. It opens
one Windows Terminal window with five named Command Prompt tabs using the existing
Python environments and Node dependencies. Windows Terminal is required.
Keep the tabs open while using the applications. Double-click `stop_all.bat` to
stop all five servers together, or press Ctrl+C in a tab to stop one server.
The self-contained `stop_all.bat` identifies this project's processes
on the five server ports and stop their child processes too. Server tabs remain
open and can be closed afterward. PostgreSQL stays running.
If a port is already occupied, stop its existing server before starting again.

| Server | Port |
| --- | --- |
| Credit Dossier MCP | 8004 |
| Credit Dossier backend | 8003 |
| Credit Dossier frontend | 8081 |
| Credit Policy Intelligence backend | 8002 |
| Credit Policy Intelligence frontend | 5173 |

Open Credit Dossier at http://localhost:8081 and Credit Policy Intelligence at
http://localhost:5173 after their terminals report that startup is complete.

First-time setup and individual startup instructions are in
[cd_cpi_server/run.md](cd_cpi_server/run.md) and [cpi_server/run.md](cpi_server/run.md).
Shared frontend components are stored in `cd_cpi_server/credit_dossier_backend/shared`.
Credit analysts see deals from all relationship managers in both applications.
Relationship managers see their own deals.
