import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https: http://localhost:8005 http://127.0.0.1:8005 ws://localhost:5174 ws://127.0.0.1:5174; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
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
    cacheDir: "node_modules/.vite-dm-dev",
    define: {"import.meta.env.VITE_APPLICATION_ID":JSON.stringify("dm")},
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
    ssr: {noExternal:["lucide-react"]},
    html: nonce ? { cspNonce: nonce } : {},
    resolve: { alias: {"@cpi":fileURLToPath(new URL("../../cpi_server/frontend/src",import.meta.url)),"lucide-react":fileURLToPath(new URL("./node_modules/lucide-react",import.meta.url))}, dedupe: ["react", "react-dom"] },
    server: { fs: { allow: [fileURLToPath(new URL("../..", import.meta.url))] }, port: 5174, strictPort: true, headers: { ...securityHeaders, "Content-Security-Policy": developmentCsp } },
    preview: { headers: securityHeaders },
  };
});
