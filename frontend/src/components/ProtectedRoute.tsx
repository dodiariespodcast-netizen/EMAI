import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth, isScheduler } from "../lib/auth";
import { Button, Spinner } from "./ui";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading, connectionError, retryBootstrap } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-brand-600">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  // A stored session we couldn't verify is not the same thing as being signed
  // out: bouncing to the login screen here would lose the user's place (and
  // look like a random logout) every time the API hiccups.
  if (!user && connectionError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm font-medium text-slate-800">Can't reach the server</p>
        <p className="max-w-sm text-xs text-slate-500">
          You're still signed in -- we just couldn't load your account. Check your connection and try again.
        </p>
        <Button onClick={retryBootstrap}>Retry</Button>
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
