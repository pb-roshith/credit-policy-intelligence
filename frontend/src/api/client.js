export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 120000;
const csrfToken = () => document.cookie
  .split("; ")
  .find((entry) => entry.startsWith("cpi_csrf="))
  ?.split("=").slice(1).join("=") || "";

export async function apiRequest(path, options = {}) {
  let response;
  let body;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  const externalSignal = options.signal;
  const abortFromExternalSignal = () => controller.abort(externalSignal.reason);
  if (externalSignal) {
    if (externalSignal.aborted) abortFromExternalSignal();
    else externalSignal.addEventListener("abort", abortFromExternalSignal, { once: true });
  }
  const method = (options.method || "GET").toUpperCase();
  const csrf = !["GET", "HEAD", "OPTIONS"].includes(method) ? csrfToken() : "";
  try {
    response = await fetch(`${API}${path}`, {
      ...options,
      signal: controller.signal,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        ...options.headers,
      },
    });
    body = await response.json().catch(() => ({}));
  } catch (error) {
    if (controller.signal.aborted && !externalSignal?.aborted) {
      throw new Error("The request timed out. Please try again.");
    }
    throw new Error("The request could not be completed. Please try again.");
  } finally {
    clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternalSignal);
  }
  if (!response.ok) {
    const message = response.status >= 500
      ? "An unexpected error occurred. Please try again later."
      : Array.isArray(body.detail)
      ? "Please check the information you entered and try again."
      : typeof body.detail === "string" && body.detail.trim()
      ? body.detail
      : "The request could not be completed. Please try again.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}
