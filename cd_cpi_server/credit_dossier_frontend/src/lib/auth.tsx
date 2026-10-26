import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiErrorFromResponse } from "@/lib/api-error";

export type AuthUser = {
  user_id: string;
  role: "relationship_manager" | "credit_analyst" | "admin";
};

export type PasswordPolicy = {
  min_length: number;
  max_length: number;
  min_uppercase: number;
  min_lowercase: number;
  min_digits: number;
  min_special: number;
};

export type AuthConfiguration = {
  password_policy: PasswordPolicy;
  security_questions: string[];
  required_security_questions: 3;
  allow_custom_security_questions: boolean;
};

export type SecurityQuestionResponse = { question: string; answer: string };

type LoginInput = { user_id: string; password: string };
type RegisterInput = LoginInput & {
  confirm_password: string;
  role: Exclude<AuthUser["role"], "admin">;
  security_questions: SecurityQuestionResponse[];
};
type ChangePasswordInput = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};
type ResetPasswordInput = {
  user_id: string;
  security_questions: SecurityQuestionResponse[];
  new_password: string;
  confirm_password: string;
};
type ConfigureSecurityQuestionsInput = {
  current_password: string;
  security_questions: SecurityQuestionResponse[];
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<AuthUser>;
  register: (input: RegisterInput) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (input: ChangePasswordInput) => Promise<string>;
  resetPassword: (input: ResetPasswordInput) => Promise<string>;
  getResetQuestions: (userId: string) => Promise<string[]>;
  configureSecurityQuestions: (input: ConfigureSecurityQuestionsInput) => Promise<string>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function authRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers as Record<string, string> | undefined),
    },
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

// This API helper intentionally lives beside the authentication provider.
// eslint-disable-next-line react-refresh/only-export-components
export async function getAuthConfiguration(): Promise<AuthConfiguration> {
  return authRequest<AuthConfiguration>("/api/auth/configuration");
}

// This API helper intentionally lives beside the authentication provider.
// eslint-disable-next-line react-refresh/only-export-components
export async function getAccountStatus(
  userId: string,
): Promise<{ status: "pending" | "not_pending"; message?: string }> {
  return authRequest<{ status: "pending" | "not_pending"; message?: string }>(
    "/api/auth/account-status",
    {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    },
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const current = await authRequest<AuthUser>("/api/auth/me");
      setUser(current);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const handleUnauthorized = () => setUser(null);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, [refresh]);

  const login = useCallback(async (input: LoginInput) => {
    const loggedIn = await authRequest<AuthUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setUser(loggedIn);
    return loggedIn;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const registered = await authRequest<AuthUser>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return registered;
  }, []);

  const changePassword = useCallback(async (input: ChangePasswordInput) => {
    const result = await authRequest<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return result.message;
  }, []);

  const resetPassword = useCallback(async (input: ResetPasswordInput) => {
    const result = await authRequest<{ message: string }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return result.message;
  }, []);

  const getResetQuestions = useCallback(async (userId: string) => {
    const result = await authRequest<{ questions: string[] }>(
      "/api/auth/reset-password/questions",
      {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      },
    );
    return result.questions;
  }, []);

  const configureSecurityQuestions = useCallback(async (input: ConfigureSecurityQuestionsInput) => {
    const result = await authRequest<{ message: string }>("/api/auth/security-questions", {
      method: "PUT",
      body: JSON.stringify(input),
    });
    return result.message;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authRequest<void>("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      changePassword,
      resetPassword,
      getResetQuestions,
      configureSecurityQuestions,
      refresh,
    }),
    [
      user,
      loading,
      login,
      register,
      logout,
      changePassword,
      resetPassword,
      getResetQuestions,
      configureSecurityQuestions,
      refresh,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// The provider and its companion hook intentionally share one small module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
