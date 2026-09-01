import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth, isScheduler } from "../lib/auth";
import { Spinner } from "./ui";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-brand-600">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function RequireScheduler({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!isScheduler(user)) return <Navigate to="/app" replace />;
  return <>{children}</>;
}
