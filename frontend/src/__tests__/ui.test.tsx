import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { ApiError, setSession } from "@/api/client";
import type { ApprovalChecklist } from "@/api/types";
import { AiBanner, BACKUP_BANNER_TEXT } from "@/components/app/AiBanner";
import { ApprovalChecklistView } from "@/components/app/ApprovalChecklistView";
import { ErrorBanner } from "@/components/app/ErrorBanner";
import { ExecutePanel } from "@/components/app/ExecutePanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { ProjectsPage } from "@/pages/ProjectsPage";

vi.mock("@/api/endpoints", () => ({
  api: { projects: vi.fn(async () => []), datasets: vi.fn(async () => []) },
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <TooltipProvider>{ui}</TooltipProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const panelProps = {
  isOperator: true,
  activeRun: null,
  faultInjectionEnabled: true,
  onExecute: () => undefined,
};

describe("frontend (spec §11)", () => {
  it("disables Execute until the version is approved", () => {
    const { rerender } = render(<ExecutePanel {...panelProps} version={{ id: 1, version_number: 2, status: "DRAFT" }} />);
    expect(screen.getByRole("button", { name: /execute/i })).toBeDisabled();
    expect(screen.getByText(/only an approved version can be executed/i)).toBeInTheDocument();

    rerender(<ExecutePanel {...panelProps} version={{ id: 1, version_number: 2, status: "APPROVED" }} />);
    expect(screen.getByRole("button", { name: /execute/i })).toBeEnabled();
  });

  it("renders checklist blockers including the self-approval warning", () => {
    const checklist: ApprovalChecklist = {
      plan_version_id: 3,
      content_hash: "a".repeat(64),
      dry_run: null,
      items: [
        { id: "role", label: "You have the approver role", ok: true, blocking: true, detail: null },
        { id: "dry_run", label: "A dry run of this exact version exists on the current data", ok: false, blocking: true, detail: "No dry run yet." },
        { id: "questions", label: "Every clarification question is answered", ok: false, blocking: true, detail: "Unanswered: Q1, Q3", missing: ["Q1", "Q3"] },
        { id: "separation_of_duties", label: "Approver is not the author of this version", ok: false, blocking: false, detail: "Self-approval: you edited this version." },
      ],
      blockers: ["dry_run", "questions"],
      can_approve: false,
      self_approval: true,
      unanswered_question_ids: ["Q1", "Q3"],
      unacknowledged_high_risk_ids: [],
    };
    render(<ApprovalChecklistView checklist={checklist} />);
    expect(screen.getByTestId("check-dry_run")).toHaveTextContent(/blocking/i);
    expect(screen.getByTestId("check-questions")).toHaveTextContent("Unanswered: Q1, Q3");
    expect(screen.getByTestId("check-separation_of_duties")).toHaveTextContent(/warning/i);
    expect(screen.getAllByText(/self-approval: you edited this version/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/2 blocking/)).toBeInTheDocument();
  });

  it("shows the error code and a request_id link to Logs", () => {
    const err = new ApiError(409, "INVALID_STATE", "The approval checklist is not complete.", {}, "req-1234abcd");
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ErrorBanner error={err} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("INVALID_STATE");
    expect(screen.getByText("The approval checklist is not complete.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "req-1234abcd" })).toHaveAttribute("href", "/logs?request_id=req-1234abcd");
  });

  it("shows the backup-AI banner when a run fell back or health is backup", () => {
    const { rerender, container } = render(<AiBanner status="primary" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<AiBanner status="primary" fellBack />);
    expect(screen.getByText(BACKUP_BANNER_TEXT)).toBeInTheDocument();
    rerender(<AiBanner status="backup" />);
    expect(screen.getByText(BACKUP_BANNER_TEXT)).toBeInTheDocument();
  });

  it("renders the empty projects state with its call to action", async () => {
    setSession({ token: "t", user: { id: 1, username: "operator", role: "operator" } });
    wrap(<ProjectsPage />);
    expect(await screen.findByText("No migrations yet. Create one from a provided dataset.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /new project/i }).length).toBeGreaterThanOrEqual(1);
  });
});
