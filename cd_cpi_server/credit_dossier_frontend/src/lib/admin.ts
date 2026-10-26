import type { PasswordPolicy } from "@/lib/auth";
import { apiErrorFromResponse } from "@/lib/api-error";

export type AuditLogEntry = {
  event_id: string;
  category: "user_event" | "administrative_action" | "system_error" | "security_alert";
  event_type: string;
  user_id: string;
  source_ip: string;
  resource_id: string;
  status: "success" | "failure" | "error";
  http_status: number;
  error_code: string | null;
  message: string | null;
  occurred_at: string;
};

export type PendingUser = {
  user_id: string;
  role: "relationship_manager" | "credit_analyst";
  created_at: string;
};

export type LockedUser = {
  user_id: string;
  role: "administrator" | "relationship_manager" | "credit_analyst";
  failed_login_attempts: number;
  locked_at: string | null;
};

async function adminRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers as Record<string, string> | undefined),
    },
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("auth:unauthorized"));
    throw await apiErrorFromResponse(response);
  }
  return response.json();
}

export function getAdminPasswordPolicy(): Promise<PasswordPolicy> {
  return adminRequest<PasswordPolicy>("/api/admin/password-policy");
}

export function updateAdminPasswordPolicy(policy: PasswordPolicy): Promise<PasswordPolicy> {
  return adminRequest<PasswordPolicy>("/api/admin/password-policy", {
    method: "PUT",
    body: JSON.stringify(policy),
  });
}

export function getAuditLogs(): Promise<AuditLogEntry[]> {
  return adminRequest<AuditLogEntry[]>("/api/admin/audit-logs");
}

export function getAdministrativeAuditLogs(): Promise<AuditLogEntry[]> {
  return adminRequest<AuditLogEntry[]>("/api/admin/administrative-audit-logs");
}

export function getPendingUserApprovals(): Promise<PendingUser[]> {
  return adminRequest<PendingUser[]>("/api/admin/user-approvals");
}

export function approveUser(userId: string): Promise<PendingUser> {
  return adminRequest<PendingUser>(
    `/api/admin/user-approvals/${encodeURIComponent(userId)}/approve`,
    { method: "POST" },
  );
}

export function getLockedUsers(): Promise<LockedUser[]> {
  return adminRequest<LockedUser[]>("/api/admin/locked-users");
}

export function unlockUser(userId: string): Promise<LockedUser> {
  return adminRequest<LockedUser>(`/api/admin/locked-users/${encodeURIComponent(userId)}/unlock`, {
    method: "POST",
  });
}

export function adminResetUserPassword(userId: string, password: string): Promise<{ message: string }> {
  return adminRequest<{ message: string }>(
    `/api/admin/locked-users/${encodeURIComponent(userId)}/reset-password`,
    {
      method: "POST",
      body: JSON.stringify({ new_password: password, confirm_password: password }),
    },
  );
}
