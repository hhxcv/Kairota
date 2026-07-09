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
  repository_id: string | null;
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

export type Repository = {
  id: string;
  provider: string;
  provider_repo_id: string;
  name: string;
  default_branch: string;
  sync_status: string;
};

export type RuntimeHealth = {
  status: string;
  service: string;
  version: string;
  database_identity: string;
};

export const sectionTones: Record<SectionId, Tone> = {
  ready: "green",
  running: "blue",
  blocked: "amber",
  waiting: "gray",
  failed: "red",
  done: "green",
};

export const sectionIds = [
  "ready",
  "running",
  "blocked",
  "waiting",
  "failed",
  "done",
] as const;

const emptySummary: QueueSummary = {
  total: 0,
  by_status: {},
  active_leases: 0,
  active_locks: 0,
};

export const emptyWorkbench: QueueWorkbench = {
  summary: emptySummary,
  sections: sectionIds.map((sectionId) => ({
    id: sectionId,
    title: titleForSection(sectionId),
    count: 0,
    rows: [],
  })),
  decision_inbox: [],
  recent_events: [],
  failures: [],
  recovery_signals: [],
};

export function titleForSection(sectionId: SectionId): string {
  return sectionId[0].toUpperCase() + sectionId.slice(1);
}

export function allRows(workbench: QueueWorkbench): QueueWorkbenchRow[] {
  return workbench.sections.flatMap((section) => section.rows);
}
