import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
  sectionIds,
  titleForSection,
  type QueueWorkbench,
  type QueueWorkbenchRow,
} from "./workbench";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

const fixtureRows: QueueWorkbenchRow[] = [
  workbenchRow({
    id: "ready-1",
    title: "Implement managed-project onboarding",
    section: "ready",
    status: "ready",
    priority: 10,
    risk: "medium",
    work_type: "implementation",
    expected_touch: "src/kairota/services/repositories.py",
    acceptance: "Repository registration and scoped ready queue are available.",
    validation: "pytest tests/test_api.py",
    conflict_keys: ["runtime:repository"],
    dependency_ids: ["done-1"],
  }),
  workbenchRow({
    id: "running-1",
    title: "Record worker lifecycle evidence",
    section: "running",
    status: "implementing",
    priority: 20,
    risk: "high",
    work_type: "implementation",
    worker_run: {
      id: "run-1",
      lease_id: "lease-1",
      role: "worker",
      status: "running",
      result: null,
      heartbeat_at: "2026-07-08T11:20:00Z",
      closed_at: null,
    },
  }),
  workbenchRow({
    id: "blocked-1",
    title: "Confirm unresolved review ownership",
    section: "blocked",
    status: "human_decision",
    priority: 30,
    risk: "medium",
    work_type: "design",
    reason_code: "blocked_by_human_decision",
    next_action: "Capture decision",
  }),
  workbenchRow({
    id: "waiting-1",
    title: "Sync PR review gate summary",
    section: "waiting",
    status: "waiting_checks",
    priority: 40,
    risk: "medium",
    work_type: "implementation",
    repository: {
      pull_request_number: 7,
      current_checks: 3,
      pending_checks: 1,
      failing_checks: 0,
      review_state: "waiting",
      unresolved_threads: 0,
    },
  }),
  workbenchRow({
    id: "failed-1",
    title: "Repair stale check reducer",
    section: "failed",
    status: "ci_failed",
    priority: 50,
    risk: "high",
    work_type: "test",
    reason_code: "blocked_by_ci",
    next_action: "Repair failing checks",
    repository: {
      pull_request_number: 8,
      current_checks: 4,
      pending_checks: 0,
      failing_checks: 1,
      review_state: "approved",
      unresolved_threads: 0,
    },
  }),
  workbenchRow({
    id: "done-1",
    title: "Merge worker run lifecycle",
    section: "done",
    status: "done",
    priority: 60,
    risk: "medium",
    work_type: "implementation",
    reason_code: "done",
    next_action: "No action",
  }),
];

const fixtureWorkbench: QueueWorkbench = {
  summary: {
    total: fixtureRows.length,
    by_status: Object.fromEntries(
      fixtureRows.map((row) => [row.status, 1]),
    ) as Record<string, number>,
    active_leases: 1,
    active_locks: 3,
  },
  sections: sectionIds.map((sectionId) => {
    const rows = fixtureRows.filter((row) => row.section === sectionId);
    return {
      id: sectionId,
      title: titleForSection(sectionId),
      count: rows.length,
      rows,
    };
  }),
  decision_inbox: fixtureRows.filter((row) =>
    ["blocked", "failed"].includes(row.section),
  ),
  recent_events: [
    {
      id: "event-1",
      kind: "audit",
      summary: "Worker run closed with result.",
      subject_type: "worker_run",
      subject_id: "run-done",
      status: "recorded",
      created_at: "2026-07-08T11:31:00Z",
      details: { result: "done" },
    },
  ],
  failures: [
    {
      id: "failure-1",
      kind: "inbound_event",
      summary: "check_run failed",
      subject_type: "inbound_event",
      subject_id: "event-failure",
      status: "failed",
      created_at: "2026-07-08T11:21:00Z",
      details: { provider: "github", action: "completed" },
    },
  ],
  recovery_signals: [
    {
      id: "failed_inbound_events",
      title: "Failed inbound events",
      severity: "warning",
      count: 1,
      action: "Inspect failed webhook or poll events",
      details: { command: "kairota queue workbench" },
    },
  ],
};

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllEnvs();
});

describe("App", () => {
  it("renders every M1 queue section from the workbench read model", async () => {
    vi.stubEnv("VITE_KAIROTA_API_BASE_URL", "https://api.example.test");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => fixtureWorkbench,
    });

    render(<App />);

    for (const title of ["Ready", "Running", "Blocked", "Waiting", "Failed", "Done"]) {
      expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "Decision Inbox" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recovery Signals" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent Events" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failures" })).toBeInTheDocument();
    expect(screen.getByText("Merge worker run lifecycle - done")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/queue/workbench",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByText(/Local API/)).toBeInTheDocument();
  });

  it("selects rows and updates the detail panel", async () => {
    vi.stubEnv("VITE_KAIROTA_API_BASE_URL", "https://api.example.test");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => fixtureWorkbench,
    });

    render(<App />);

    await screen.findByRole("heading", { name: "Failed" });
    fireEvent.click(
      screen.getAllByRole("button", { name: /repair stale check reducer/i })[0],
    );

    const detail = screen.getByLabelText("Selected work item");
    expect(
      within(detail).getByRole("heading", { name: "Repair stale check reducer" }),
    ).toBeInTheDocument();
    expect(within(detail).getByText("blocked_by_ci")).toBeInTheDocument();
    expect(within(detail).getByText(/1 failing/)).toBeInTheDocument();
  });

  it("keeps search-filtered counts and decision inbox consistent", async () => {
    vi.stubEnv("VITE_KAIROTA_API_BASE_URL", "https://api.example.test");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => fixtureWorkbench,
    });

    render(<App />);

    await screen.findByRole("heading", { name: "Ready" });
    fireEvent.change(screen.getByLabelText("Search work items"), {
      target: { value: "managed-project" },
    });

    expect(screen.getByText(/1 visible work items \(6 total\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ready1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Blocked0" })).toBeInTheDocument();

    const decisionInbox = screen.getByRole("region", { name: "Decision Inbox" });
    expect(within(decisionInbox).getByText("0")).toBeInTheDocument();
    expect(
      screen.queryByText("Confirm unresolved review ownership"),
    ).not.toBeInTheDocument();
  });

  it("shows an empty queue state when the API is unavailable", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));

    render(<App />);

    expect(await screen.findByText(/API unavailable/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/No API data/)).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Implement managed-project onboarding"),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("No work")).toHaveLength(sectionIds.length);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/queue/workbench",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });
});

function workbenchRow(
  overrides: Partial<QueueWorkbenchRow> &
    Pick<QueueWorkbenchRow, "id" | "section" | "title">,
): QueueWorkbenchRow {
  return {
    status: "ready",
    priority: 10,
    risk: "medium",
    work_type: "implementation",
    autonomy_mode: "ai_assisted",
    expected_touch: null,
    acceptance: null,
    validation: null,
    source_url: null,
    conflict_keys: [],
    dependency_ids: [],
    reason_code: "ready_for_claim",
    next_action: "Run scheduler or claim",
    worker_run: null,
    repository_id: "repository-1",
    repository: {},
    ...overrides,
  };
}
