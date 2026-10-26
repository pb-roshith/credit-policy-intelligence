import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LogOut,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";

import { PasswordPolicyChecklist } from "@/components/PasswordPolicyChecklist";
import { SecurityQuestionFields } from "@/components/SecurityQuestionFields";
import {
  getAuthConfiguration,
  type AuthConfiguration,
  type SecurityQuestionResponse,
  useAuth,
} from "@/lib/auth";

export const Route = createFileRoute("/profile")({
  head: () => ({ meta: [{ title: "Profile | Credit Pitch Book" }] }),
  component: ProfilePage,
});

function ProfilePage() {
  const { user, changePassword, configureSecurityQuestions, logout } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [configuration, setConfiguration] = useState<AuthConfiguration | null>(null);
  const [securityResponses, setSecurityResponses] = useState<SecurityQuestionResponse[]>([]);
  const [securityPassword, setSecurityPassword] = useState("");
  const [savingQuestions, setSavingQuestions] = useState(false);
  const [questionMessage, setQuestionMessage] = useState<string | null>(null);
  const [questionError, setQuestionError] = useState<string | null>(null);

  useEffect(() => {
    getAuthConfiguration()
      .then((result) => {
        setConfiguration(result);
        setSecurityResponses(
          result.security_questions.slice(0, 3).map((question) => ({ question, answer: "" })),
        );
      })
      // Security: do not expose backend error details to users.
      .catch(() => setQuestionError("Unable to load security settings."));
  }, []);

  const blockClipboard = (event: React.ClipboardEvent<HTMLInputElement>) => event.preventDefault();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("New password and confirm password must match.");
      return;
    }
    setSaving(true);
    try {
      setMessage(
        await changePassword({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      // Do not surface authentication or backend details from a failed request.
      setError("Password change failed. Verify your current password and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    await logout();
    await navigate({ to: "/login", replace: true });
  }

  async function submitSecurityQuestions(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuestionError(null);
    setQuestionMessage(null);
    setSavingQuestions(true);
    try {
      setQuestionMessage(
        await configureSecurityQuestions({
          current_password: securityPassword,
          security_questions: securityResponses,
        }),
      );
      setSecurityPassword("");
      setSecurityResponses((current) => current.map((item) => ({ ...item, answer: "" })));
    } catch {
      // Security-question failures can contain confidential authentication details.
      setQuestionError("Unable to update security questions. Verify your password and try again.");
    } finally {
      setSavingQuestions(false);
    }
  }

  function updateSecurityResponse(
    index: number,
    field: keyof SecurityQuestionResponse,
    value: string,
  ) {
    setSecurityResponses((current) =>
      current.map((response, responseIndex) =>
        responseIndex === index ? { ...response, [field]: value } : response,
      ),
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <div className="doc-card overflow-hidden">
        <div className="flex items-center gap-4 border-b bg-primary/5 p-6">
          <div className="rounded-full bg-primary p-3 text-primary-foreground">
            <UserRound className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{user?.user_id}</h1>
            <p className="text-sm text-muted-foreground">
              {user?.role === "relationship_manager"
                ? "Relationship Manager"
                : user?.role === "admin"
                  ? "Administrator"
                  : "Credit Analyst"}
            </p>
          </div>
          <button
            onClick={signOut}
            className="ml-auto inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted"
          >
            <LogOut className="h-4 w-4" /> Logout
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4 p-6">
          <div className="flex items-center gap-2 font-semibold">
            <KeyRound className="h-4 w-4" /> Change password
          </div>
          {[
            ["Current password", currentPassword, setCurrentPassword],
            ["New password", newPassword, setNewPassword],
            ["Confirm new password", confirmPassword, setConfirmPassword],
          ].map(([label, value, setter]) => (
            <label key={label as string} className="block space-y-1.5 text-sm font-medium">
              {label as string}
              <div className="relative">
                <input
                  type={visiblePasswords[label as string] ? "text" : "password"}
                  autoComplete="off"
                  required
                  minLength={
                    label === "Current password" ? 1 : configuration?.password_policy.min_length
                  }
                  maxLength={
                    label === "Current password"
                      ? 128
                      : Math.min(31, configuration?.password_policy.max_length ?? 31)
                  }
                  value={value as string}
                  onChange={(event) =>
                    (setter as React.Dispatch<React.SetStateAction<string>>)(event.target.value)
                  }
                  onCopy={blockClipboard}
                  onCut={blockClipboard}
                  onPaste={blockClipboard}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 pr-10 font-normal outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                  type="button"
                  onClick={() =>
                    setVisiblePasswords((current) => ({
                      ...current,
                      [label as string]: !current[label as string],
                    }))
                  }
                  className="absolute right-0 top-0 flex h-10 w-10 items-center justify-center text-muted-foreground"
                  aria-label={`${visiblePasswords[label as string] ? "Hide" : "Show"} ${(label as string).toLowerCase()}`}
                >
                  {visiblePasswords[label as string] ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </label>
          ))}
          {configuration && (
            <PasswordPolicyChecklist
              password={newPassword}
              policy={configuration.password_policy}
              userId={user?.user_id}
            />
          )}
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {message && (
            <div className="flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" />
              {message}
            </div>
          )}
          <button
            disabled={saving}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save password
          </button>
        </form>

        <form onSubmit={submitSecurityQuestions} className="space-y-4 border-t p-6">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-4 w-4" /> Configure password recovery
          </div>
          <p className="text-sm text-muted-foreground">
            Choose three different questions. Saving replaces any questions configured previously.
          </p>
          <SecurityQuestionFields
            responses={securityResponses}
            options={configuration?.security_questions ?? []}
            onChange={updateSecurityResponse}
            allowCustomQuestions={configuration?.allow_custom_security_questions ?? false}
          />
          <label className="block space-y-1.5 text-sm font-medium">
            Current password
            <input
              required
              type="password"
              autoComplete="off"
              value={securityPassword}
              onChange={(event) => setSecurityPassword(event.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          {questionError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {questionError}
            </div>
          )}
          {questionMessage && (
            <div className="flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" /> {questionMessage}
            </div>
          )}
          <button
            disabled={savingQuestions || !configuration}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {savingQuestions && <Loader2 className="h-4 w-4 animate-spin" />} Save security
            questions
          </button>
        </form>
      </div>
    </main>
  );
}
