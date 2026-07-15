import type {
  IssuePage,
  IssueQuery,
  ManagedIssue,
  Project,
  RuntimeHealth,
} from "./domain";

export const API_BASE_URL = "http://127.0.0.1:8010";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function fetchHealth(signal?: AbortSignal): Promise<RuntimeHealth> {
  return request<RuntimeHealth>("/healthz", { signal });
}

export function fetchProjects(signal?: AbortSignal): Promise<Project[]> {
  return request<Project[]>("/projects", { signal });
}

export function fetchIssues(
  query: IssueQuery,
  signal?: AbortSignal,
): Promise<IssuePage> {
  const params = new URLSearchParams();
  for (const projectId of query.projectIds) {
    params.append("project_id", projectId);
  }
  for (const state of query.states) {
    params.append("state", state);
  }
  if (query.query.trim()) {
    params.set("query", query.query.trim());
  }
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return request<IssuePage>(`/issues?${params.toString()}`, { signal });
}

export function fetchIssue(
  issueId: string,
  signal?: AbortSignal,
): Promise<ManagedIssue> {
  return request<ManagedIssue>(`/issues/${encodeURIComponent(issueId)}`, { signal });
}

export function createProject(remote: string): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({ remote }),
  });
}

export function syncProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${encodeURIComponent(projectId)}/sync`, {
    method: "POST",
    headers: commandHeaders(),
  });
}

function commandHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "Idempotency-Key": createIdempotencyKey(),
  };
}

function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string; explanation?: string };
      detail = payload.explanation ?? payload.detail ?? "";
    } catch {
      // The status remains useful when an error response has no JSON body.
    }
    throw new ApiError(detail || `Request failed with ${response.status}`, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
