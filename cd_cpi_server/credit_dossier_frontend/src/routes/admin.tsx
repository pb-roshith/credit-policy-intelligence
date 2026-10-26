import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, KeyRound, Loader2, LockKeyhole, Save, ShieldCheck, Unlock, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";

import {
  getAdminPasswordPolicy,
  getAuditLogs,
  getPendingUserApprovals,
  approveUser,
  adminResetUserPassword,
  getLockedUsers,
  unlockUser,
  updateAdminPasswordPolicy,
  type AuditLogEntry,
  type PendingUser,
  type LockedUser,
} from "@/lib/admin";
import type { PasswordPolicy } from "@/lib/auth";

export const Route = createFileRoute("/admin")({
  head: () => ({ meta: [{ title: "Admin dashboard | Credit Pitch Book" }] }),
  component: AdminDashboard,
});

const POLICY_FIELDS: Array<{
  key: keyof PasswordPolicy;
  label: string;
  description: string;
  minimum: number;
}> = [
  {
    key: "min_length",
    label: "Minimum password length",
    description: "Choose at least 12 characters, up to the configured maximum.",
    minimum: 12,
  },
  {
    key: "max_length",
    label: "Maximum password length",
    description: "Choose at most 31 characters, at or above the configured minimum.",
    minimum: 12,
  },
  {
    key: "min_uppercase",
    label: "Required uppercase letters",
    description: "Set to 0 to disable the uppercase requirement.",
    minimum: 0,
  },
  {
    key: "min_lowercase",
    label: "Required lowercase letters",
    description: "Set to 0 to disable the lowercase requirement.",
    minimum: 0,
  },
  {
    key: "min_digits",
    label: "Required digits",
    description: "Set to 0 to disable the numeric requirement.",
    minimum: 0,
  },
  {
    key: "min_special",
    label: "Required special characters",
    description: "Set to 0 to disable the special-character requirement.",
    minimum: 0,
  },
];

function AdminDashboard() {
  const [policy, setPolicy] = useState<PasswordPolicy | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [queueLoading, setQueueLoading] = useState(true);
  const [approvingUserId, setApprovingUserId] = useState<string | null>(null);
  const [lockedUsers, setLockedUsers] = useState<LockedUser[]>([]);
  const [lockedUsersLoading, setLockedUsersLoading] = useState(true);
  const [accountActionUserId, setAccountActionUserId] = useState<string | null>(null);

  useEffect(() => {
    getAdminPasswordPolicy()
      .then(setPolicy)
      .catch((requestError) =>
        setError(requestError instanceof Error ? requestError.message : "Unable to load policy."),
      );
    getAuditLogs()
      .then(setAuditEvents)
      .catch((requestError) =>
        setError(
          requestError instanceof Error ? requestError.message : "Unable to load audit trail.",
        ),
      )
      .finally(() => setAuditLoading(false));
    getPendingUserApprovals()
      .then(setPendingUsers)
      .catch((requestError) =>
        setError(
          requestError instanceof Error ? requestError.message : "Unable to load approval queue.",
        ),
      )
      .finally(() => setQueueLoading(false));
    getLockedUsers()
      .then(setLockedUsers)
      .catch((requestError) =>
        setError(requestError instanceof Error ? requestError.message : "Unable to load locked accounts."),
      )
      .finally(() => setLockedUsersLoading(false));
  }, []);

  async function unlock(userId: string) {
    setAccountActionUserId(userId);
    setError(null);
    try {
      await unlockUser(userId);
      setLockedUsers((current) => current.filter((user) => user.user_id !== userId));
      setMessage(`${userId} was unlocked.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to unlock account.");
    } finally {
      setAccountActionUserId(null);
    }
  }

  async function resetLockedPassword(userId: string) {
    const password = window.prompt(`Enter a new temporary password for ${userId}:`);
    if (!password) return;
    setAccountActionUserId(userId);
    setError(null);
    try {
      const result = await adminResetUserPassword(userId, password);
      setLockedUsers((current) => current.filter((user) => user.user_id !== userId));
      setMessage(result.message);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reset password.");
    } finally {
      setAccountActionUserId(null);
    }
  }

  async function approve(userId: string) {
    setApprovingUserId(userId);
    setError(null);
    setMessage(null);
    try {
      await approveUser(userId);
      setPendingUsers((current) => current.filter((user) => user.user_id !== userId));
      setMessage(`${userId} was approved and can now sign in.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to approve user.");
    } finally {
      setApprovingUserId(null);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    if (!Number.isInteger(policy.min_length) || !Number.isInteger(policy.max_length) ||
        policy.min_length < 12 || policy.max_length > 31 || policy.min_length > policy.max_length) {
      setError("Password lengths must satisfy 12 ≤ minimum ≤ maximum ≤ 31.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      setPolicy(await updateAdminPasswordPolicy(policy));
      setMessage("Password policy saved successfully.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save policy.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-primary">
          <ShieldCheck className="h-6 w-6" />
          <span className="text-sm font-semibold uppercase tracking-wide">Administration</span>
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Admin dashboard</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Manage application-wide password requirements. Administrators cannot create deals, access
          deal workspaces, or generate narratives.
        </p>
      </div>

      <section className="doc-card mb-6 overflow-hidden">
        <div className="border-b bg-primary/5 p-6">
          <h2 className="flex items-center gap-2 font-semibold">
            <UserCheck className="h-5 w-5" /> User approval queue
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Review newly registered users. Approved accounts can sign in immediately.
          </p>
        </div>
        {queueLoading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading approval queue…
          </div>
        ) : pendingUsers.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">
            No accounts are waiting for approval.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Requested role</th>
                  <th>Registered</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {pendingUsers.map((pendingUser) => (
                  <tr key={pendingUser.user_id}>
                    <td className="font-mono text-sm">{pendingUser.user_id}</td>
                    <td>
                      {pendingUser.role === "relationship_manager"
                        ? "Relationship Manager"
                        : "Credit Analyst"}
                    </td>
                    <td className="whitespace-nowrap text-sm">
                      {new Date(pendingUser.created_at).toLocaleString()}
                    </td>
                    <td>
                      <button
                        type="button"
                        disabled={approvingUserId !== null}
                        onClick={() => void approve(pendingUser.user_id)}
                        className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-60"
                      >
                        {approvingUserId === pendingUser.user_id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4" />
                        )}
                        Approve
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="doc-card mb-6 overflow-hidden">
        <div className="border-b bg-primary/5 p-6">
          <h2 className="flex items-center gap-2 font-semibold"><LockKeyhole className="h-5 w-5" /> Locked accounts</h2>
          <p className="mt-1 text-sm text-muted-foreground">Accounts lock after three failed sign-in attempts. Unlock them or assign a new password.</p>
        </div>
        {lockedUsersLoading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading locked accounts…</div>
        ) : lockedUsers.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No accounts are locked.</p>
        ) : (
          <div className="overflow-x-auto"><table className="doc-table"><thead><tr><th>User ID</th><th>Role</th><th>Locked</th><th>Actions</th></tr></thead><tbody>
            {lockedUsers.map((lockedUser) => <tr key={lockedUser.user_id}>
              <td className="font-mono text-sm">{lockedUser.user_id}</td><td>{lockedUser.role.replaceAll("_", " ")}</td>
              <td className="whitespace-nowrap text-sm">{lockedUser.locked_at ? new Date(lockedUser.locked_at).toLocaleString() : "—"}</td>
              <td><div className="flex gap-2">
                <button type="button" disabled={accountActionUserId !== null} onClick={() => void unlock(lockedUser.user_id)} className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-60"><Unlock className="h-4 w-4" /> Unlock</button>
                <button type="button" disabled={accountActionUserId !== null} onClick={() => void resetLockedPassword(lockedUser.user_id)} className="inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-medium disabled:opacity-60"><KeyRound className="h-4 w-4" /> Reset password</button>
              </div></td>
            </tr>)}
          </tbody></table></div>
        )}
      </section>

      <form onSubmit={submit} className="doc-card overflow-hidden">
        <div className="border-b bg-primary/5 p-6">
          <h2 className="font-semibold">Password configuration</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Saved values immediately apply to registration, password changes, and password resets.
          </p>
        </div>

        {!policy ? (
          <div className="flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading password policy…
          </div>
        ) : (
          <div className="grid gap-5 p-6 sm:grid-cols-2">
            {POLICY_FIELDS.map((field) => (
              <label key={field.key} className="block space-y-1.5 text-sm font-medium">
                {field.label}
                <input
                  required
                  type="number"
                  min={field.minimum}
                  max={31}
                  step={1}
                  value={policy[field.key]}
                  onChange={(event) =>
                    setPolicy((current) =>
                      current
                        ? {
                            ...current,
                            [field.key]: Number.parseInt(event.target.value || "0", 10),
                          }
                        : current,
                    )
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
                />
                <span className="block text-xs font-normal text-muted-foreground">
                  {field.description}
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="space-y-3 border-t p-6">
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {message && (
            <div className="flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" /> {message}
            </div>
          )}
          <button
            disabled={!policy || saving}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save password policy
          </button>
        </div>
      </form>

      <AdministrativeAuditTrail
        events={auditEvents.filter((event) => event.category === "administrative_action")}
        loading={auditLoading}
      />

      <section className="doc-card mt-6 overflow-hidden">
        <div className="border-b bg-primary/5 p-6">
          <h2 className="font-semibold">System audit trail</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Complete user-event and system-error history, shown newest first in your local time.
          </p>
        </div>
        {auditLoading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading audit trail…
          </div>
        ) : auditEvents.filter((event) => event.category !== "administrative_action").length ===
          0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">
            No audit events have been recorded yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>Date and time</th>
                  <th>Category</th>
                  <th>Event ID</th>
                  <th>Source IP</th>
                  <th>User ID</th>
                  <th>Resource ID</th>
                  <th>Event</th>
                  <th>Error code</th>
                  <th>Status</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents
                  .filter((event) => event.category !== "administrative_action")
                  .map((event) => (
                    <tr key={event.event_id}>
                      <td className="whitespace-nowrap text-sm">
                        {new Date(event.occurred_at).toLocaleString()}
                      </td>
                      <td>
                        <span
                          className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${
                            event.category === "security_alert"
                              ? "border-amber-300 bg-amber-50 text-amber-800"
                              : event.category === "system_error"
                              ? "border-red-300 bg-red-50 text-red-700"
                              : "border-blue-300 bg-blue-50 text-blue-700"
                          }`}
                        >
                          {event.category === "security_alert"
                            ? "Security alert"
                            : event.category === "system_error"
                              ? "System error"
                              : "User event"}
                        </span>
                      </td>
                      <td className="max-w-48 truncate font-mono text-xs" title={event.event_id}>
                        {event.event_id}
                      </td>
                      <td className="whitespace-nowrap font-mono text-sm">{event.source_ip}</td>
                      <td className="font-mono text-sm">{event.user_id}</td>
                      <td className="max-w-64 truncate font-mono text-xs" title={event.resource_id}>
                        {event.resource_id}
                      </td>
                      <td className="text-sm">
                        <div>{event.event_type.replaceAll("_", " ")}</div>
                        <div className="text-xs text-muted-foreground">
                          HTTP {event.http_status}
                        </div>
                      </td>
                      <td className="whitespace-nowrap font-mono text-xs">
                        {event.error_code ?? "—"}
                      </td>
                      <td>
                        <span
                          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                            event.status === "success"
                              ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                              : "border-red-300 bg-red-50 text-red-700"
                          }`}
                        >
                          {event.status === "success"
                            ? "Success"
                            : event.status === "error"
                              ? "Error"
                              : "Failure"}
                        </span>
                      </td>
                      <td className="max-w-80 truncate text-xs" title={event.message ?? ""}>
                        {event.message ?? "—"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function AdministrativeAuditTrail({
  events,
  loading,
}: {
  events: AuditLogEntry[];
  loading: boolean;
}) {
  return (
    <section className="doc-card mt-6 overflow-hidden">
      <div className="border-b bg-primary/5 p-6">
        <h2 className="font-semibold">Administrative action audit trail</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Administrator activity is maintained separately and shown newest first in your local time.
        </p>
      </div>
      {loading ? (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading administrative audit trail…
        </div>
      ) : events.length === 0 ? (
        <p className="p-8 text-center text-sm text-muted-foreground">
          No administrative actions have been recorded yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="doc-table">
            <thead>
              <tr>
                <th>Date and time</th>
                <th>Category</th>
                <th>Event ID</th>
                <th>Source IP</th>
                <th>Administrator ID</th>
                <th>Resource ID</th>
                <th>Action</th>
                <th>Error code</th>
                <th>Status</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.event_id}>
                  <td className="whitespace-nowrap text-sm">
                    {new Date(event.occurred_at).toLocaleString()}
                  </td>
                  <td>
                    <span className="inline-flex whitespace-nowrap rounded-full border border-purple-300 bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                      Administrative action
                    </span>
                  </td>
                  <td className="max-w-48 truncate font-mono text-xs" title={event.event_id}>
                    {event.event_id}
                  </td>
                  <td className="whitespace-nowrap font-mono text-sm">{event.source_ip}</td>
                  <td className="font-mono text-sm">{event.user_id}</td>
                  <td className="max-w-64 truncate font-mono text-xs" title={event.resource_id}>
                    {event.resource_id}
                  </td>
                  <td className="text-sm">
                    <div>{event.event_type.replaceAll("_", " ")}</div>
                    <div className="text-xs text-muted-foreground">HTTP {event.http_status}</div>
                  </td>
                  <td className="whitespace-nowrap font-mono text-xs">
                    {event.error_code ?? "—"}
                  </td>
                  <td>
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                        event.status === "success"
                          ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                          : "border-red-300 bg-red-50 text-red-700"
                      }`}
                    >
                      {event.status === "success"
                        ? "Success"
                        : event.status === "error"
                          ? "Error"
                          : "Failure"}
                    </span>
                  </td>
                  <td className="max-w-80 truncate text-xs" title={event.message ?? ""}>
                    {event.message ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
