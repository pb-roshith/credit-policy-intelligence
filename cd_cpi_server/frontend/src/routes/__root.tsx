import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  useRouterState,
  useNavigate,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { AppHeader } from "../components/AppHeader";
import { AuthProvider, useAuth } from "../lib/auth";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  if (import.meta.env.DEV) console.error(error);
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Credit Dossier Dashboard" },
      { name: "description", content: "Credit Dossier Management Dashboard" },
      { name: "author", content: "Credit Dossier" },
      { property: "og:title", content: "Credit Dossier Dashboard" },
      { property: "og:description", content: "Credit Dossier Management Dashboard" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthenticatedApp />
      </AuthProvider>
    </QueryClientProvider>
  );
}

function AuthenticatedApp() {
  const { user, loading } = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const isLogin = pathname === "/login";
  const isAdminDashboard = pathname === "/admin";
  const isProfile = pathname === "/profile";
  const adminOutsideAllowedPages =
    user?.role === "admin" && !isLogin && !isAdminDashboard && !isProfile;
  const nonAdminOnAdminDashboard = Boolean(user && user.role !== "admin" && isAdminDashboard);

  useEffect(() => {
    if (loading) return;
    if (!user && !isLogin) void navigate({ to: "/login", replace: true });
    if (user && isLogin) {
      void navigate({ to: user.role === "admin" ? "/admin" : "/", replace: true });
    }
    if (adminOutsideAllowedPages) void navigate({ to: "/admin", replace: true });
    if (nonAdminOnAdminDashboard) void navigate({ to: "/", replace: true });
  }, [user, loading, isLogin, adminOutsideAllowedPages, nonAdminOnAdminDashboard, navigate]);

  if (
    loading ||
    (!user && !isLogin) ||
    (user && isLogin) ||
    adminOutsideAllowedPages ||
    nonAdminOnAdminDashboard
  ) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (isLogin) return <Outlet />;

  return (
    <div className="min-h-screen bg-surface">
      <AppHeader />
      <Outlet />
    </div>
  );
}
