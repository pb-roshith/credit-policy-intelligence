export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export async function apiRequest(path, options = {}, token = "") {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = Array.isArray(body.detail)
      ? body.detail.map((item) => item.msg || item).join(". ")
      : body.detail || "Something went wrong";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}


