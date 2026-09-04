# Frontend

Run `npm install`, then `npm run dev`.

The responsive single-page React app recreates the seven supplied workspaces:

- Executive Dashboard
- Credit Requests
- Policy Intelligence
- Compliance Review
- Exception Management
- Decision Simulator
- Portfolio Analytics

Navigation uses URL hashes, so each workspace can be linked directly (for example,
`http://localhost:5173/#simulator`). Set `VITE_API_URL` to override the default API
location of `http://localhost:8000`.
