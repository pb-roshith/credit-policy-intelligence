export type ApiErrorEnvelope = {
  error_code?: string;
  detail?: string;
  event_id?: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode?: string,
    readonly eventId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiErrorFromResponse(
  response: Response,
  fallback = "The request could not be completed.",
): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as ApiErrorEnvelope | null;
  const detail = typeof body?.detail === "string" ? body.detail : fallback;
  const identifiers = [
    body?.error_code,
    body?.event_id ? `Reference: ${body.event_id}` : null,
  ].filter(Boolean);
  const message = identifiers.length > 0 ? `${detail} (${identifiers.join("; ")})` : detail;

  return new ApiError(message, response.status, body?.error_code, body?.event_id);
}
