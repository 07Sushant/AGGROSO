import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/app/AppShell";
import { useAuth } from "@/lib/auth";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { LogsPage } from "@/pages/LogsPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { SchemaImportPage } from "@/pages/SchemaImportPage";
import { ProjectLayout } from "@/pages/workspace/ProjectLayout";
import { AgentStep } from "@/pages/workspace/AgentStep";
import { ApproveStep } from "@/pages/workspace/ApproveStep";
import { DryRunStep } from "@/pages/workspace/DryRunStep";
import { ExecuteStep } from "@/pages/workspace/ExecuteStep";
import { HistoryStep } from "@/pages/workspace/HistoryStep";
import { InputsStep } from "@/pages/workspace/InputsStep";
import { OverviewStep } from "@/pages/workspace/OverviewStep";
import { PlanStep } from "@/pages/workspace/PlanStep";

function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <AppShell />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route index element={<OverviewStep />} />
          <Route path="inputs" element={<InputsStep />} />
          <Route path="agent" element={<AgentStep />} />
          <Route path="plan" element={<PlanStep />} />
          <Route path="dry-run" element={<DryRunStep />} />
          <Route path="approve" element={<ApproveStep />} />
          <Route path="execute" element={<ExecuteStep />} />
          <Route path="history" element={<HistoryStep />} />
        </Route>
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/schema-import" element={<SchemaImportPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
