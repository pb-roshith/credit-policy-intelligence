import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { BookOpen, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { PasswordPolicyChecklist } from "@/components/PasswordPolicyChecklist";
import { SecurityQuestionFields } from "@/components/SecurityQuestionFields";
import {
  getAuthConfiguration,
  getAccountStatus,
  type AuthConfiguration,
  type SecurityQuestionResponse,
  useAuth,
} from "@/lib/auth";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Sign in | Credit Pitch Book" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { login, register, resetPassword, getResetQuestions } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register" | "reset">("login");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"relationship_manager" | "credit_analyst">("credit_analyst");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [configuration, setConfiguration] = useState<AuthConfiguration | null>(null);
  const [securityResponses, setSecurityResponses] = useState<SecurityQuestionResponse[]>([]);
  const [resetQuestionsLoaded, setResetQuestionsLoaded] = useState(false);
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);

  useEffect(() => {
    getAuthConfiguration()
      .then((result) => {
        setConfiguration(result);
        setSecurityResponses(
          result.security_questions.slice(0, 3).map((question) => ({ question, answer: "" })),
        );
      })
      // Security: do not expose backend error details to users.
      .catch(() => setError("Unable to load password policy."));
  }, []);

  useEffect(() => {
    setApprovalMessage(null);
    const normalizedUserId = userId.trim().toLowerCase();
    if (
      mode !== "login" ||
      normalizedUserId.length < 3 ||
      !/^[a-z0-9._-]+$/.test(normalizedUserId)
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      getAccountStatus(normalizedUserId)
        .then((result) =>
          setApprovalMessage(
            result.status === "pending" ? "This account is awaiting administrator approval." : null,
          ),
        )
        .catch(() => setApprovalMessage(null));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [mode, userId]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (userId.length > 64 || password.length > (mode === "login" ? 128 : 31) || confirmPassword.length > 31) {
      setError("User IDs can contain up to 64 characters. New passwords can contain up to 31 characters.");
      return;
    }
    if (mode === "reset" && !resetQuestionsLoaded) {
      setSubmitting(true);
      try {
        const questions = await getResetQuestions(userId.trim());
        setSecurityResponses(questions.map((question) => ({ question, answer: "" })));
        setResetQuestionsLoaded(true);
      } catch {
        // Keep recovery failures generic to avoid exposing account or backend details.
        setError("Unable to continue with password recovery.");
      } finally {
        setSubmitting(false);
      }
      return;
    }
    if (mode !== "login" && password !== confirmPassword) {
      setError("New password and confirm password must match.");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "login") {
        const loggedIn = await login({ user_id: userId.trim(), password });
        await navigate({ to: loggedIn.role === "admin" ? "/admin" : "/" });
        return;
      } else if (mode === "register") {
        await register({
          user_id: userId.trim(),
          password,
          confirm_password: confirmPassword,
          role,
          security_questions: securityResponses,
        });
        setSuccess("Account created successfully and sent to the admin queue for approval.");
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setShowPassword(false);
        setShowConfirmPassword(false);
        return;
      } else {
        await resetPassword({
          user_id: userId.trim(),
          security_questions: securityResponses,
          new_password: password,
          confirm_password: confirmPassword,
        });
        setSuccess("Password reset successfully. You can now sign in.");
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setShowPassword(false);
        setShowConfirmPassword(false);
        return;
      }
    } catch {
      // Authentication responses may contain confidential implementation or account details.
      setError(
        mode === "login"
          ? "Sign-in failed. Check your credentials and try again."
          : mode === "register"
            ? "Unable to create the account. Review your entries and try again."
            : "Unable to reset the password. Verify your answers and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode: "login" | "register" | "reset") {
    setMode(nextMode);
    setError(null);
    setSuccess(null);
    setConfirmPassword("");
    setShowPassword(false);
    setShowConfirmPassword(false);
    setResetQuestionsLoaded(false);
    setApprovalMessage(null);
    if (configuration) {
      setSecurityResponses(
        configuration.security_questions.slice(0, 3).map((question) => ({ question, answer: "" })),
      );
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

  const showPasswordFields = mode !== "reset" || resetQuestionsLoaded;

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.25),transparent_36%),radial-gradient(circle_at_bottom_right,rgba(14,116,144,0.18),transparent_34%)]" />
      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-white shadow-2xl md:grid-cols-[1.05fr_1fr]">
        <section className="hidden bg-primary p-10 text-primary-foreground md:flex md:flex-col md:justify-between">
          <div className="flex items-center gap-3 text-xl font-semibold">
            <span className="rounded-lg bg-white/10 p-2">
              <BookOpen className="h-6 w-6" />
            </span>
            Credit Pitch Book
          </div>
          <div>
            <ShieldCheck className="mb-5 h-10 w-10 opacity-90" />
            <h1 className="text-3xl font-bold leading-tight">Secure credit dossier workspace</h1>
            <p className="mt-3 text-sm leading-6 text-primary-foreground/75">
              Create, review, and finalize private credit narratives with secure access to
              manufacturing tools.
            </p>
          </div>
          <p className="text-xs text-primary-foreground/60">Credit Dossier Pipeline</p>
        </section>

        <section className="p-6 sm:p-10">
          <div className="mb-7 md:hidden">
            <div className="flex items-center gap-2 font-semibold text-primary">
              <BookOpen className="h-5 w-5" /> Credit Pitch Book
            </div>
          </div>
          <h2 className="text-2xl font-bold tracking-tight">
            {mode === "login"
              ? "Welcome back"
              : mode === "register"
                ? "Create your account"
                : "Reset your password"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "login"
              ? "Use the same user ID and password for Credit Dossier and CPI."
              : mode === "register"
                ? "Create one account for Credit Dossier and CPI, with administrator approval."
                : resetQuestionsLoaded
                  ? "Answer all three recovery questions to reset your password for both applications."
                  : "Enter your user ID to retrieve your recovery questions."}
          </p>

          <form className="mt-7 space-y-4" onSubmit={submit}>
            <label className="block space-y-1.5 text-sm font-medium">
              User ID
              <input
                autoComplete="off"
                required
                minLength={3}
                maxLength={64}
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                className="h-11 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
                placeholder="Enter your user ID"
              />
            </label>
            {showPasswordFields && (
              <label className="block space-y-1.5 text-sm font-medium">
                {mode === "reset" ? "New password" : "Password"}
                <div className="relative">
                  <input
                    autoComplete="off"
                    required
                    minLength={mode === "login" ? 1 : configuration?.password_policy.min_length}
                    maxLength={
                      mode === "login" ? 128 : Math.min(31, configuration?.password_policy.max_length ?? 31)
                    }
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    onCopy={(event) => event.preventDefault()}
                    onCut={(event) => event.preventDefault()}
                    onPaste={(event) => event.preventDefault()}
                    className="h-11 w-full rounded-md border border-input bg-background px-3 pr-11 font-normal outline-none focus:ring-2 focus:ring-ring"
                    placeholder={
                      mode === "login"
                        ? "Enter your password"
                        : `Minimum ${configuration?.password_policy.min_length ?? "configured"} characters`
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </label>
            )}

            {mode !== "login" && showPasswordFields && (
              <label className="block space-y-1.5 text-sm font-medium">
                Confirm {mode === "reset" ? "new " : ""}password
                <div className="relative">
                  <input
                    autoComplete="off"
                    required
                    minLength={configuration?.password_policy.min_length}
                    maxLength={Math.min(31, configuration?.password_policy.max_length ?? 31)}
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    onCopy={(event) => event.preventDefault()}
                    onCut={(event) => event.preventDefault()}
                    onPaste={(event) => event.preventDefault()}
                    className="h-11 w-full rounded-md border border-input bg-background px-3 pr-11 font-normal outline-none focus:ring-2 focus:ring-ring"
                    placeholder="Re-enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((value) => !value)}
                    className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground"
                    aria-label={
                      showConfirmPassword ? "Hide confirm password" : "Show confirm password"
                    }
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </label>
            )}

            {mode === "register" && (
              <>
                <label className="block space-y-1.5 text-sm font-medium">
                  Role
                  <select
                    value={role}
                    onChange={(event) =>
                      setRole(event.target.value as "relationship_manager" | "credit_analyst")
                    }
                    className="h-11 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value="credit_analyst">Credit Analyst</option>
                    <option value="relationship_manager">Relationship Manager</option>
                  </select>
                </label>
                <SecurityQuestionFields
                  responses={securityResponses}
                  options={configuration?.security_questions ?? []}
                  onChange={updateSecurityResponse}
                  allowCustomQuestions={configuration?.allow_custom_security_questions ?? false}
                />
              </>
            )}

            {mode === "reset" && resetQuestionsLoaded && (
              <SecurityQuestionFields
                responses={securityResponses}
                options={[]}
                onChange={updateSecurityResponse}
                questionsReadOnly
              />
            )}

            {mode === "login" && (
              <div className="text-right">
                <button
                  type="button"
                  onClick={() => changeMode("reset")}
                  className="text-sm font-semibold text-primary hover:underline"
                >
                  Forgot password?
                </button>
              </div>
            )}

            {mode !== "login" && showPasswordFields && configuration && (
              <PasswordPolicyChecklist
                password={password}
                policy={configuration.password_policy}
                userId={userId}
              />
            )}

            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                {error}
              </div>
            )}

            {mode === "login" && approvalMessage && (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                {approvalMessage}
              </div>
            )}

            {success && (
              <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700">
                {success}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || (mode !== "login" && !configuration)}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {submitting
                ? "Please wait…"
                : mode === "login"
                  ? "Sign in"
                  : mode === "register"
                    ? "Create account"
                    : resetQuestionsLoaded
                      ? "Reset password"
                      : "Continue"}
            </button>
          </form>

          <div className="mt-6 border-t pt-5 text-center text-sm text-muted-foreground">
            {mode === "login" ? "New to the application?" : "Return to the login page?"}{" "}
            <button
              type="button"
              onClick={() => changeMode(mode === "login" ? "register" : "login")}
              className="font-semibold text-primary hover:underline"
            >
              {mode === "login" ? "Create new user" : "Sign in"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
