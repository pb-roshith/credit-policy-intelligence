import { CheckCircle2, Circle } from "lucide-react";

import type { PasswordPolicy } from "@/lib/auth";

type PolicyCheck = { label: string; met: boolean };

function passwordPolicyChecks(
  password: string,
  policy: PasswordPolicy,
  userId = "",
): PolicyCheck[] {
  const count = (pattern: RegExp) => password.match(pattern)?.length ?? 0;
  const checks: PolicyCheck[] = [
    {
      label: `At least ${policy.min_length} characters`,
      met: password.length >= policy.min_length,
    },
    {
      label: `No more than ${policy.max_length} characters`,
      met: password.length <= policy.max_length,
    },
  ];
  const characterRules: Array<[number, string, RegExp]> = [
    [policy.min_uppercase, "uppercase letter", /[A-Z]/g],
    [policy.min_lowercase, "lowercase letter", /[a-z]/g],
    [policy.min_digits, "number", /\d/g],
    [policy.min_special, "special character", /[^A-Za-z0-9]/g],
  ];
  for (const [required, label, pattern] of characterRules) {
    if (required > 0) {
      checks.push({
        label: `At least ${required} ${label}${required === 1 ? "" : "s"}`,
        met: count(pattern) >= required,
      });
    }
  }
  if (userId.trim()) {
    checks.push({
      label: "Does not contain your user ID",
      met: !password.toLowerCase().includes(userId.trim().toLowerCase()),
    });
  }
  return checks;
}

export function PasswordPolicyChecklist({
  password,
  policy,
  userId,
}: {
  password: string;
  policy: PasswordPolicy;
  userId?: string;
}) {
  const checks = passwordPolicyChecks(password, policy, userId);
  const meetsPolicy = checks.every((check) => check.met);
  return (
    <div className="rounded-md border bg-muted/35 p-3" aria-live="polite">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs font-semibold">
        <span>Password requirements</span>
        {password && (
          <span className={meetsPolicy ? "text-emerald-700" : "text-amber-700"}>
            {meetsPolicy ? "Strong enough" : "Does not meet policy"}
          </span>
        )}
      </div>
      <ul className="grid gap-1 text-xs sm:grid-cols-2">
        {checks.map((check) => (
          <li
            key={check.label}
            className={`flex items-center gap-1.5 ${check.met ? "text-emerald-700" : "text-muted-foreground"}`}
          >
            {check.met ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <Circle className="h-3.5 w-3.5" />
            )}
            {check.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
