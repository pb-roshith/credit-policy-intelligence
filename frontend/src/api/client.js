export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const csrfToken = () => document.cookie
  .split("; ")
  .find((entry) => entry.startsWith("cpi_csrf="))
  ?.split("=").slice(1).join("=") || "";

export async function apiRequest(path, options = {}) {
  let response;
  const method = (options.method || "GET").toUpperCase();
  const csrf = !["GET", "HEAD", "OPTIONS"].includes(method) ? csrfToken() : "";
  try {
    response = await fetch(`${API}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("The request could not be completed. Please try again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = response.status >= 500
      ? "An unexpected error occurred. Please try again later."
      : Array.isArray(body.detail)
      ? body.detail.map((item) => item.msg || item).join(". ")
      : body.detail || "Something went wrong";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}
