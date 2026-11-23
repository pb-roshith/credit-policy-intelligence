# Error code book

This reference covers error codes emitted by Credit Policy Intelligence. User and administrator audit logs pair each code with an event ID, timestamp, action, outcome, severity, and available account and request information. Use the event ID and timestamp to correlate an error with application diagnostics.

## Request and authentication audit codes

| Code | HTTP status | Meaning | Operator action |
|---|---:|---|---|
| `INVALID_CREDENTIALS` | 401 | A sign-in attempt was rejected. | Review repeated failures for the account or source IP. |
| `REQUEST_VALIDATION_FAILED` | 422 | The request failed schema validation. | Check the client request against the API contract. |
| `REQUEST_BODY_NOT_ALLOWED` | 400 | A GET or HEAD request included a body. | Use the endpoint's supported submission method. |
| `REQUEST_TOO_LARGE` | 413 | The request body exceeded the configured size limit. | Check the upload size and applicable endpoint limit. |
| `RATE_LIMIT_EXCEEDED` | 429 | The request exceeded the application's rate limit. | Check request volume and have the client honor `Retry-After`. |
| `DATABASE_UNAVAILABLE` | 503 | The PostgreSQL driver raised an operational error. | Check database availability, connectivity, and server diagnostics. |
| `DATABASE_ERROR` | 500 | The PostgreSQL driver raised another database error. | Correlate the timestamp with database and application diagnostics. |
| `UNHANDLED_SERVER_ERROR` | 500 | An unexpected application exception reached the default handler. | Investigate the corresponding server diagnostic entry. |
| `HTTP_<status>` | Varies | A handled HTTP failure. The suffix is the response status, for example `HTTP_401`, `HTTP_403`, or `HTTP_502`. | Use the status, audit action, and resource or route to narrow the cause. |

A single rejected sign-in may produce an `INVALID_CREDENTIALS` entry and an `HTTP_401` entry. Failed password resets use the `PASSWORD_RESET` audit action with the applicable request error code.

## Background jobs and warning logs

| Code or marker | Where it appears | Meaning |
|---|---|---|
| `QUALITY_REVIEW_FAILED` | Agent execution log | An advisory rule quality review failed. |
| `Worker interrupted` | Inventory agent execution log | A stale worker was marked as failed. Inventory jobs can resume from completed batches on retry. |
| Exception class or validation diagnostic | Agent execution, quality report, or extraction attempt log | Some background workflows store the original diagnostic or exception class in the `error_code` field. Use the associated job, batch, or execution ID to investigate. |
| `CPI_SECURITY_ALERT` | Application warning log | A threshold was reached for `credential_failures`, `access_denials`, `rate_limit_violations`, or `server_failures`. |

Keep codes stable for log searches. When adding a named code, document its trigger and operator action here.
