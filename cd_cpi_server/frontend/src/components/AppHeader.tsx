import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BookOpen,
  LayoutDashboard,
  FilePlus2,
  Factory,
  LogOut,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

export function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isDashboard = pathname === "/" || pathname === "/dashboard";
  const isNew = pathname.startsWith("/deals/new");
  const isManufacture = pathname.startsWith("/manufacture-data");
  const isObservability = pathname.startsWith("/observability");
  const isAdmin = user?.role === "admin";
  const isAdminDashboard = pathname === "/admin";

  const tabCls = (active: boolean) =>
    `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
      active ? "bg-primary-foreground/15" : "hover:bg-primary-foreground/10"
    }`;

  async function handleLogout() {
    await logout();
    await navigate({ to: "/login", replace: true });
  }

  return (
    <header className="border-b bg-primary text-primary-foreground">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-3 py-2 sm:px-6">
        <div className="flex items-center gap-1">
          <Link
            to={isAdmin ? "/admin" : "/"}
            className="flex items-center gap-2 rounded-md px-3 py-2 font-semibold"
          >
            <BookOpen className="h-5 w-5" />
            <span>Credit Pitch Book</span>
          </Link>
          {isAdmin ? (
            <Link to="/admin" className={tabCls(isAdminDashboard)}>
              <ShieldCheck className="h-4 w-4" /> Admin Dashboard
            </Link>
          ) : (
            <>
              <Link to="/" className={tabCls(isDashboard)}>
                <LayoutDashboard className="h-4 w-4" /> Dashboard
              </Link>
              {user?.role === "relationship_manager" && (
                <Link to="/deals/new" className={tabCls(isNew)}>
                  <FilePlus2 className="h-4 w-4" /> New Deal
                </Link>
              )}
              <Link to="/manufacture-data" className={tabCls(isManufacture)}>
                <Factory className="h-4 w-4" /> Manufacture Data
              </Link>
              <Link to="/observability" className={tabCls(isObservability)}>
                <Activity className="h-4 w-4" /> Observability
              </Link>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/profile"
            className="rounded-md px-2 py-1 text-right text-xs leading-tight hover:bg-primary-foreground/10"
          >
            <div className="flex items-center justify-end gap-1 font-semibold">
              <UserRound className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{user?.user_id}</span>
            </div>
            <div className="hidden opacity-75 sm:block">
              {user?.role === "relationship_manager"
                ? "Relationship Manager"
                : user?.role === "admin"
                  ? "Administrator"
                  : "Credit Analyst"}
            </div>
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex items-center gap-2 rounded-md border border-primary-foreground/25 px-3 py-2 text-sm font-medium hover:bg-primary-foreground/10"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
}
