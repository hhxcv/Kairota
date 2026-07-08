export type SectionId =
  | "ready"
  | "running"
  | "blocked"
  | "waiting"
  | "failed"
  | "done";

export type Tone = "green" | "blue" | "amber" | "red" | "gray";

export type QueueSummary = {
  total: number;
  by_status: Record<string, number>;
  active_leases: number;
  active_locks: number;
};

export type QueueWorkbenchRun = {
  id: string;
  lease_id: string | null;
  role: string;
  status: string;
  result: string | null;
  heartbeat_at: string | null;
  closed_at: string | null;
};

export type QueueWorkbenchRow = {
  id: string;
  title: string;
  section: SectionId;
  status: string;
  priority: number;
  risk: string;
  work_type: string;
  autonomy_mode: string;
  expected_touch: string | null;
  acceptance: string | null;
  validation: string | null;
  source_url: string | null;
  conflict_keys: string[];
  dependency_ids: string[];
  reason_code: string;
  next_action: string;
  worker_run: QueueWorkbenchRun | null;
  repository: Record<string, unknown>;
};

export type QueueWorkbenchSection = {
  id: SectionId;
  title: string;
  count: number;
  rows: QueueWorkbenchRow[];
};

export type QueueWorkbenchEvent = {
  id: string;
  kind: string;
  summary: string;
  subject_type: string | null;
  subject_id: string | null;
  status: string | null;
  created_at: string | null;
  details: Record<string, unknown>;
};

export type QueueWorkbenchRecoverySignal = {
  id: string;
  title: string;
  severity: string;
  count: number;
  action: string;
  details: Record<string, unknown>;
};

export type QueueWorkbench = {
  summary: QueueSummary;
  sections: QueueWorkbenchSection[];
  decision_inbox: QueueWorkbenchRow[];
  recent_events: QueueWorkbenchEvent[];
  failures: QueueWorkbenchEvent[];
  recovery_signals: QueueWorkbenchRecoverySignal[];
};

export const sectionTones: Record<SectionId, Tone> = {
  ready: "green",
  running: "blue",
  blocked: "amber",
  waiting: "gray",
  failed: "red",
  done: "green",
};

const emptySummary: QueueSummary = {
  total: 0,
  by_status: {},
  active_leases: 0,
  active_locks: 0,
};

const demoRows: QueueWorkbenchRow[] = [
  {
    id: "demo-ready",
    title: "Add queue workbench browser smoke",
    section: "ready",
    status: "ready",
    priority: 10,
    risk: "medium",
    work_type: "implementation",
    autonomy_mode: "ai_assisted",
    expected_touch: "web/src/**",
    acceptance: "Queue sections and detail panel render from API data.",
    validation: "npm run build; browser smoke",
    source_url: null,
    conflict_keys: ["runtime:frontend"],
    dependency_ids: [],
    reason_code: "ready_for_claim",
    next_action: "Run scheduler or claim",
    worker_run: null,
    repository: {},
  },
  {
    id: "demo-running",
    title: "Record worker lifecycle evidence",
    section: "running",
    status: "implementing",
    priority: 20,
    risk: "high",
    work_type: "implementation",
    autonomy_mode: "fully_autonomous",
    expected_touch: "src/kairota/services/worker_runs.py",
    acceptance: "Worker reports validation and closes with lease authority.",
    validation: "pytest tests/test_worker_runs.py",
    source_url: null,
    conflict_keys: ["runtime:worker"],
    dependency_ids: ["demo-ready"],
    reason_code: "worker_running",
    next_action: "Report progress",
    worker_run: {
      id: "run-demo",
      lease_id: "lease-demo",
      role: "worker",
      status: "running",
      result: null,
      heartbeat_at: "2026-07-08T11:20:00Z",
      closed_at: null,
    },
    repository: {},
  },
  {
    id: "demo-blocked",
    title: "Confirm unresolved review ownership",
    section: "blocked",
    status: "human_decision",
    priority: 30,
    risk: "medium",
    work_type: "design",
    autonomy_mode: "human_required",
    expected_touch: "docs/architecture/m1-ai-dev-queue.md",
    acceptance: "Decision is recorded before scheduling resumes.",
    validation: "governance check",
    source_url: null,
    conflict_keys: ["governance:review"],
    dependency_ids: [],
    reason_code: "blocked_by_human_decision",
    next_action: "Capture decision",
    worker_run: null,
    repository: {},
  },
  {
    id: "demo-waiting",
    title: "Sync PR review gate summary",
    section: "waiting",
    status: "waiting_checks",
    priority: 40,
    risk: "medium",
    work_type: "implementation",
    autonomy_mode: "ai_assisted",
    expected_touch: "src/kairota/adapters/github/**",
    acceptance: "Current-head checks and review gate are visible.",
    validation: "adapter fixture tests",
    source_url: null,
    conflict_keys: ["adapter:github"],
    dependency_ids: [],
    reason_code: "waiting_checks",
    next_action: "Wait for current-head checks",
    worker_run: null,
    repository: {
      pull_request_number: 7,
      current_checks: 3,
      pending_checks: 1,
      failing_checks: 0,
      review_state: "waiting",
      unresolved_threads: 0,
    },
  },
  {
    id: "demo-failed",
    title: "Repair stale check reducer",
    section: "failed",
    status: "ci_failed",
    priority: 50,
    risk: "high",
    work_type: "test",
    autonomy_mode: "ai_assisted",
    expected_touch: "tests/test_github_sync.py",
    acceptance: "Failed checks are reduced without using stale head SHA.",
    validation: "pytest tests/test_github_sync.py",
    source_url: null,
    conflict_keys: ["adapter:github"],
    dependency_ids: [],
    reason_code: "blocked_by_ci",
    next_action: "Repair failing checks",
    worker_run: null,
    repository: {
      pull_request_number: 8,
      current_checks: 4,
      pending_checks: 0,
      failing_checks: 1,
      review_state: "approved",
      unresolved_threads: 0,
    },
  },
  {
    id: "demo-done",
    title: "Merge M1 worker run lifecycle",
    section: "done",
    status: "done",
    priority: 60,
    risk: "medium",
    work_type: "implementation",
    autonomy_mode: "fully_autonomous",
    expected_touch: "src/kairota/services/worker_runs.py",
    acceptance: "PR merged with tests and AI review requested.",
    validation: "53 backend tests; web build",
    source_url: null,
    conflict_keys: ["runtime:worker"],
    dependency_ids: [],
    reason_code: "done",
    next_action: "No action",
    worker_run: {
      id: "run-done",
      lease_id: "lease-done",
      role: "worker",
      status: "closed",
      result: "done",
      heartbeat_at: "2026-07-08T11:30:00Z",
      closed_at: "2026-07-08T11:31:00Z",
    },
    repository: { pull_request_number: 7, merged: true },
  },
];

export const demoWorkbench: QueueWorkbench = {
  summary: {
    ...emptySummary,
    total: demoRows.length,
    by_status: Object.fromEntries(
      demoRows.map((row) => [row.status, 1]),
    ) as Record<string, number>,
    active_leases: 1,
    active_locks: 3,
  },
  sections: (["ready", "running", "blocked", "waiting", "failed", "done"] as const).map(
    (sectionId) => {
      const rows = demoRows.filter((row) => row.section === sectionId);
      return {
        id: sectionId,
        title: titleForSection(sectionId),
        count: rows.length,
        rows,
      };
    },
  ),
  decision_inbox: demoRows.filter((row) =>
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
    {
      id: "event-2",
      kind: "audit",
      summary: "Repository summary marked stale after head change.",
      subject_type: "pull_request",
      subject_id: "pr-8",
      status: "recorded",
      created_at: "2026-07-08T11:26:00Z",
      details: { stale: true },
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
    {
      id: "stale_repository_gates",
      title: "Stale repository gates",
      severity: "warning",
      count: 1,
      action: "Refresh repository summaries",
      details: { command: "kairota sync repository" },
    },
  ],
};

export function titleForSection(sectionId: SectionId): string {
  return sectionId[0].toUpperCase() + sectionId.slice(1);
}

export function allRows(workbench: QueueWorkbench): QueueWorkbenchRow[] {
  return workbench.sections.flatMap((section) => section.rows);
}
