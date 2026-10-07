import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { randomBytes } from "node:crypto";

const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https: http://localhost:8000 http://127.0.0.1:8000 ws://localhost:5173 ws://127.0.0.1:5173; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
const securityHeaders = {
  "Content-Security-Policy": csp,
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cache-Control": "no-store, max-age=0",
};

export default defineConfig(({ command, isPreview }) => {
  // React Refresh injects an inline module in development. Both CSP policies
  // must authorize the nonce that Vite adds to that module.
  const nonce = command === "serve" && !isPreview
    ? randomBytes(18).toString("base64")
    : null;
  const developmentCsp = nonce
    ? csp.replace("script-src 'self'", `script-src 'self' 'nonce-${nonce}'`)
    : csp;

  return {
    plugins: [
      react(),
      {
        name: "development-csp",
        transformIndexHtml: {
          order: "pre",
          handler: (html) => nonce ? html.replace(csp, developmentCsp) : html,
        },
      },
    ],
    html: nonce ? { cspNonce: nonce } : {},
    server: { headers: { ...securityHeaders, "Content-Security-Policy": developmentCsp } },
    preview: { headers: securityHeaders },
  };
});
