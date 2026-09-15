# Frontend

Run `npm install`, then `npm run dev`.

The responsive single-page React app provides these workspaces:

- Executive Dashboard
- Credit Requests
- Policy Intelligence
- Compliance Review
- Exception Management
- Decision Simulator
- Portfolio Analytics
- Data Manufacturing

Navigation uses URL hashes, so each workspace can be linked directly (for example,
`http://localhost:5173/#simulator`). Set `VITE_API_URL` to override the default API
location of `http://localhost:8000`.

The frontend source is organized by responsibility:

- `src/main.jsx` only mounts the application.
- `src/Shell.jsx` owns navigation, authentication state, and page selection.
- `src/pages/` contains one module per workspace or account screen.
- `src/components/` contains reusable UI elements.
- `src/api/` contains the backend client, while `src/config.js` contains shared display configuration.
