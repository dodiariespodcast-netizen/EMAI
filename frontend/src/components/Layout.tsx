import { NavLink, Outlet } from "react-router-dom";
import { useAuth, isScheduler } from "../lib/auth";

interface NavItem {
  to: string;
  label: string;
  schedulerOnly?: boolean;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/app", label: "Dashboard", end: true },
  { to: "/app/schedule", label: "Schedule" },
  { to: "/app/requests", label: "Time Off" },
  { to: "/app/preferences", label: "Preferences" },
  { to: "/app/swaps", label: "Shift Swaps" },
  { to: "/app/compliance", label: "Compliance" },
  { to: "/app/roster", label: "Roster", schedulerOnly: true },
  { to: "/app/shifts", label: "Sites & Shifts", schedulerOnly: true },
  { to: "/app/generate", label: "Generate Schedule", schedulerOnly: true },
  { to: "/app/rules", label: "Scheduling Rules", schedulerOnly: true },
  { to: "/app/reports", label: "Reports", schedulerOnly: true },
  { to: "/app/users", label: "Users", schedulerOnly: true },
  { to: "/app/audit", label: "Audit Log", schedulerOnly: true },
  { to: "/app/settings", label: "Settings" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const scheduler = isScheduler(user);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
            E
          </div>
          <span className="text-sm font-semibold text-slate-900">EMAI Scheduler</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.filter((item) => !item.schedulerOnly || scheduler).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 px-4 py-4">
          <p className="truncate text-xs font-medium text-slate-700">{user?.email}</p>
          <p className="text-xs capitalize text-slate-400">{user?.role}</p>
          <button onClick={logout} className="mt-2 text-xs font-medium text-slate-400 hover:text-red-600">
            Log out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <span className="text-sm font-semibold">EMAI Scheduler</span>
          <button onClick={logout} className="text-xs font-medium text-slate-500">
            Log out
          </button>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
