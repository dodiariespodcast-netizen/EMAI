import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import { ProtectedRoute, RequireScheduler } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { SetPasswordPage } from "./pages/SetPasswordPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SchedulePage } from "./pages/SchedulePage";
import { RequestsPage } from "./pages/RequestsPage";
import { PreferencesPage } from "./pages/PreferencesPage";
import { SwapsPage } from "./pages/SwapsPage";
import { CompliancePage } from "./pages/CompliancePage";
import { RosterPage } from "./pages/RosterPage";
import { ShiftsPage } from "./pages/ShiftsPage";
import { GeneratePage } from "./pages/GeneratePage";
import { RulesPage } from "./pages/RulesPage";
import { UsersPage } from "./pages/UsersPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<SetPasswordPage mode="reset" />} />
          <Route path="/set-password" element={<SetPasswordPage mode="invite" />} />

          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="schedule" element={<SchedulePage />} />
            <Route path="requests" element={<RequestsPage />} />
            <Route path="preferences" element={<PreferencesPage />} />
            <Route path="swaps" element={<SwapsPage />} />
            <Route path="compliance" element={<CompliancePage />} />
            <Route path="settings" element={<SettingsPage />} />

            <Route
              path="roster"
              element={
                <RequireScheduler>
                  <RosterPage />
                </RequireScheduler>
              }
            />
            <Route
              path="shifts"
              element={
                <RequireScheduler>
                  <ShiftsPage />
                </RequireScheduler>
              }
            />
            <Route
              path="generate"
              element={
                <RequireScheduler>
                  <GeneratePage />
                </RequireScheduler>
              }
            />
            <Route
              path="rules"
              element={
                <RequireScheduler>
                  <RulesPage />
                </RequireScheduler>
              }
            />
            <Route
              path="users"
              element={
                <RequireScheduler>
                  <UsersPage />
                </RequireScheduler>
              }
            />
            <Route
              path="reports"
              element={
                <RequireScheduler>
                  <ReportsPage />
                </RequireScheduler>
              }
            />
            <Route
              path="audit"
              element={
                <RequireScheduler>
                  <AuditLogPage />
                </RequireScheduler>
              }
            />
          </Route>

          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
