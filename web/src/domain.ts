export const schedulingStates = [
  "needs_analysis",
  "blocked",
  "ready",
  "in_progress",
  "closed",
] as const;

export type SchedulingState = (typeof schedulingStates)[number];
export type SourceState = "open" | "closed";
export type SyncHealth = "unknown" | "syncing" | "healthy" | "error";

export type RuntimeHealth = {
  status: string;
  service: string;
  version: string;
};

export type ProjectSyncState = {
  health: SyncHealth;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
};

export type Project = {
  id: string;
  provider_repo_id: string;
  name: string;
  enabled: boolean;
  sync: ProjectSyncState;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IssueDependency = {
  issue_id: string;
  number: number;
  title: string;
  source_state: SourceState;
  url: string;
};

export type ManagedIssue = {
  id: string;
  project_id: string;
  number: number;
  title: string;
  url: string;
  source_state: SourceState;
  scheduling_state: SchedulingState;
  scheduling_version: number;
  analysis_version: number;
  analysis_completed: boolean;
  manual_hold_reason: string | null;
  in_progress_since: string | null;
  source_updated_at?: string | null;
  last_synced_at: string | null;
  dependencies: IssueDependency[];
  dependency_closed_count: number;
  blocking_reasons: string[];
  claimable_now: boolean;
  claim_block_reason: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IssuePage = {
  items: ManagedIssue[];
  total: number;
  page: number;
  page_size: number;
  by_state: Partial<Record<SchedulingState, number>>;
};

export type IssueQuery = {
  projectIds: string[];
  states: SchedulingState[];
  query: string;
  page: number;
  pageSize: number;
};

export const stateLabels: Record<SchedulingState, string> = {
  needs_analysis: "Needs analysis",
  blocked: "Blocked",
  ready: "Ready",
  in_progress: "In progress",
  closed: "Closed",
};
