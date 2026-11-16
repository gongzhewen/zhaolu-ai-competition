import { Spin } from "antd";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { getToken } from "@/lib/api/client";

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const AdmissionsOverviewPage = lazy(() => import("@/pages/AdmissionsOverviewPage"));
const AdmissionsPlansPage = lazy(() => import("@/pages/AdmissionsPlansPage"));
const SourceOverviewPage = lazy(() => import("@/pages/SourceOverviewPage"));
const DataImportPage = lazy(() => import("@/pages/DataImportPage"));
const DataDbfPage = lazy(() => import("@/pages/DataDbfPage"));
const DataQualityPage = lazy(() => import("@/pages/DataQualityPage"));
const MajorAliasesPage = lazy(() => import("@/pages/MajorAliasesPage"));
const AiAssistantPage = lazy(() => import("@/pages/AiAssistantPage"));
const AiInsightsPage = lazy(() => import("@/pages/AiInsightsPage"));
const AnalyticsAnomaliesPage = lazy(() => import("@/pages/AnalyticsAnomaliesPage"));
const AnalyticsSimulationPage = lazy(() => import("@/pages/AnalyticsSimulationPage"));
const ReportsPage = lazy(() => import("@/pages/ReportsPage"));
const ForecastOverviewPage = lazy(() => import("@/pages/ForecastOverviewPage"));
const SystemUsersPage = lazy(() => import("@/pages/SystemUsersPage"));
const SystemRolesPage = lazy(() => import("@/pages/SystemRolesPage"));
const SystemStudentsPage = lazy(() => import("@/pages/SystemStudentsPage"));
const SystemAuditPage = lazy(() => import("@/pages/SystemAuditPage"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));

function RouteLoading() {
  return (
    <div className="route-loading">
      <Spin />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function ProtectedShell() {
  return (
    <RequireAuth>
      <AppShell>
        <Suspense fallback={<RouteLoading />}>
          <Outlet />
        </Suspense>
      </AppShell>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/admissions/overview" element={<AdmissionsOverviewPage />} />
          <Route path="/admissions/plans" element={<AdmissionsPlansPage />} />
          <Route path="/source/overview" element={<SourceOverviewPage />} />
          <Route path="/data/import" element={<DataImportPage />} />
          <Route path="/data/dbf" element={<DataDbfPage />} />
          <Route path="/data/quality" element={<DataQualityPage />} />
          <Route path="/data/major-aliases" element={<MajorAliasesPage />} />
          <Route path="/ai/assistant" element={<AiAssistantPage />} />
          <Route path="/ai/insights" element={<AiInsightsPage />} />
          <Route path="/analytics/anomalies" element={<AnalyticsAnomaliesPage />} />
          <Route path="/analytics/simulation" element={<AnalyticsSimulationPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/forecast/overview" element={<ForecastOverviewPage />} />
          <Route path="/system/users" element={<SystemUsersPage />} />
          <Route path="/system/roles" element={<SystemRolesPage />} />
          <Route path="/system/students" element={<SystemStudentsPage />} />
          <Route path="/system/audit" element={<SystemAuditPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );
}
