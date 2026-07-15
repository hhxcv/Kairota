import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { API_BASE_URL } from "./api";
import {
  schedulingStates,
  type IssuePage,
  type ManagedIssue,
  type Project,
  type SchedulingState,
} from "./domain";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

const projects: Project[] = [
  project("project-alpha", "acme/alpha", "healthy"),
  project("project-beta", "acme/beta", "healthy"),
  project("project-gamma", "acme/gamma", "error"),
  project("project-delta", "acme/delta", "unknown"),
  project("project-epsilon", "acme/epsilon", "healthy"),
  project("project-zeta", "acme/zeta", "healthy"),
  project("project-eta", "acme/eta", "healthy"),
];

const issues: ManagedIssue[] = [
  issue({
    id: "issue-analysis",
    number: 11,
    title: "Map dependency graph",
    scheduling_state: "needs_analysis",
    analysis_completed: false,
  }),
  issue({
    id: "issue-blocked",
    number: 12,
    title: "Implement blocked workflow",
    scheduling_state: "blocked",
    dependencies: [
      {
        issue_id: "dependency-10",
        number: 10,
        title: "Define scheduler contract",
        source_state: "open",
        url: "https://github.com/acme/alpha/issues/10",
      },
    ],
    blocking_reasons: ["dependency_issue_open"],
  }),
  issue({
    id: "issue-ready",
    number: 13,
    title: "Build ready Issue endpoint",
    scheduling_state: "ready",
    claimable_now: true,
  }),
  issue({
    id: "issue-progress",
    project_id: "project-beta",
    number: 21,
    title: "Run managed project work",
    scheduling_state: "in_progress",
    in_progress_since: "2026-07-10T01:00:00Z",
  }),
  issue({
    id: "issue-closed",
    project_id: "project-beta",
    number: 22,
    title: "Close delivered Issue",
    source_state: "closed",
    scheduling_state: "closed",
  }),
];

beforeEach(() => {
  fetchMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Issue scheduling board", () => {
  it("supports searchable multi-project selection and all five status filters", async () => {
    installApiMock();
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Issues" })).toBeInTheDocument();
    const statusFilter = screen.getByRole("navigation", { name: "Issue status" });
    for (const label of ["Needs analysis", "Blocked", "Ready", "In progress", "Closed"]) {
      expect(within(statusFilter).getByRole("button", { name: new RegExp(label, "i") })).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: "All projects" }));
    const projectFilter = screen.getByLabelText("Project filter");
    fireEvent.change(within(projectFilter).getByLabelText("Search projects"), {
      target: { value: "alpha" },
    });
    fireEvent.click(within(projectFilter).getByRole("checkbox", { name: /acme\/alpha/i }));
    fireEvent.change(within(projectFilter).getByLabelText("Search projects"), {
      target: { value: "beta" },
    });
    fireEvent.click(within(projectFilter).getByRole("checkbox", { name: /acme\/beta/i }));

    await waitFor(() => {
      const url = latestIssueRequest();
      expect(url.searchParams.getAll("project_id")).toEqual([
        "project-alpha",
        "project-beta",
      ]);
    });
    expect(screen.getByRole("button", { name: /2 selected/i })).toBeInTheDocument();

    fireEvent.click(within(statusFilter).getByRole("button", { name: /Blocked/i }));
    await waitFor(() => {
      expect(latestIssueRequest().searchParams.getAll("state")).toEqual(["blocked"]);
    });
    expect(await screen.findByText("Implement blocked workflow")).toBeInTheDocument();
    expect(screen.queryByText("Build ready Issue endpoint")).not.toBeInTheDocument();

    fireEvent.click(within(projectFilter).getByRole("button", { name: "Clear selection" }));
    await waitFor(() => expect(latestIssueRequest().searchParams.getAll("project_id")).toEqual([]));
  });

  it("registers a project with a unique idempotency key and refreshes the board", async () => {
    const state = installApiMock();
    render(<App />);

    await screen.findByRole("heading", { name: "Issues" });
    fireEvent.click(screen.getByRole("button", { name: "Add project" }));
    const dialog = screen.getByRole("dialog", { name: "Add project" });
    fireEvent.change(within(dialog).getByLabelText("GitHub repository"), {
      target: { value: "acme/new-project" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add project" }));

    await waitFor(() => expect(state.createdRemotes).toEqual(["acme/new-project"]));
    const actualCreateCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input) === `${API_BASE_URL}/projects` && init?.method === "POST",
    );
    expect(actualCreateCall).toBeDefined();
    const headers = new Headers(actualCreateCall?.[1]?.headers);
    expect(headers.get("Idempotency-Key")).toMatch(/\S+/);
    expect(JSON.parse(String(actualCreateCall?.[1]?.body))).toEqual({ remote: "acme/new-project" });
    expect(await screen.findByText(/acme\/new-project synchronized/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(latestIssueRequest().searchParams.getAll("project_id")).toEqual(["project-new"]);
    });
  });

  it("shows a useful empty state without seeded data", async () => {
    installApiMock({ issueItems: [] });
    render(<App />);

    expect(await screen.findByText("No Issues synchronized")).toBeInTheDocument();
    expect(screen.getByText("Add a project or synchronize a registered project.")).toBeInTheDocument();
    expect(screen.queryByText("Build ready Issue endpoint")).not.toBeInTheDocument();
  });

  it("shows an API error with a working retry control", async () => {
    const state = installApiMock({ failIssues: true });
    render(<App />);

    expect(await screen.findByText("Issues could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("scheduler unavailable")).toBeInTheDocument();
    state.failIssues = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Build ready Issue endpoint")).toBeInTheDocument();
  });

  it("opens current Issue facts and dependencies in a contextual detail panel", async () => {
    installApiMock();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /Implement blocked workflow/i }));
    const detail = await screen.findByLabelText("Issue details");
    expect(within(detail).getByRole("heading", { name: "Implement blocked workflow" })).toBeInTheDocument();
    expect(within(detail).getByText("Define scheduler contract")).toBeInTheDocument();
    expect(within(detail).getByText("Dependency issue open")).toBeInTheDocument();
    expect(within(detail).getByRole("link", { name: /Open on GitHub/i })).toHaveAttribute(
      "href",
      "https://github.com/acme/alpha/issues/12",
    );
    fireEvent.click(within(detail).getByRole("button", { name: "Close issue details" }));
    expect(screen.queryByLabelText("Issue details")).not.toBeInTheDocument();
  });

  it("requests and renders subsequent pages", async () => {
    installApiMock({ total: 60 });
    render(<App />);

    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(latestIssueRequest().searchParams.get("page")).toBe("2"));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    expect(screen.getByText("26-50 of 60")).toBeInTheDocument();
  });

  it("manually synchronizes a project with its own idempotency key", async () => {
    installApiMock();
    render(<App />);

    await screen.findByRole("heading", { name: "Issues" });
    fireEvent.click(screen.getByRole("button", { name: "All projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Sync acme/alpha" }));

    await waitFor(() => {
      const syncCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith("/projects/project-alpha/sync") && init?.method === "POST",
      );
      expect(syncCall).toBeDefined();
      expect(new Headers(syncCall?.[1]?.headers).get("Idempotency-Key")).toMatch(/\S+/);
    });
    expect(await screen.findByText("acme/alpha synchronized.")).toBeInTheDocument();
  });
});

type ApiMockOptions = {
  issueItems?: ManagedIssue[];
  total?: number;
  failIssues?: boolean;
};

function installApiMock(options: ApiMockOptions = {}) {
  const state = {
    projects: [...projects],
    issueItems: options.issueItems ?? issues,
    total: options.total,
    failIssues: options.failIssues ?? false,
    createdRemotes: [] as string[],
  };

  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/healthz") {
      return jsonResponse({ status: "ok", service: "Kairota", version: "0.2.0" });
    }
    if (url.pathname === "/projects" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { remote: string };
      state.createdRemotes.push(payload.remote);
      const created = project("project-new", "acme/new-project", "unknown");
      state.projects.push(created);
      return jsonResponse(created);
    }
    if (url.pathname === "/projects") {
      return jsonResponse(state.projects);
    }
    if (url.pathname.endsWith("/sync") && init?.method === "POST") {
      return jsonResponse({ project_id: "project-alpha", status: "healthy" });
    }
    if (url.pathname.startsWith("/issues/") && !url.pathname.endsWith("/issues/")) {
      const id = decodeURIComponent(url.pathname.slice("/issues/".length));
      const detail = state.issueItems.find((item) => item.id === id);
      return detail ? jsonResponse(detail) : jsonResponse({ detail: "Not found" }, 404);
    }
    if (url.pathname === "/issues") {
      if (state.failIssues) {
        return jsonResponse({ detail: "scheduler unavailable" }, 503);
      }
      const selectedProjects = url.searchParams.getAll("project_id");
      const selectedStates = url.searchParams.getAll("state") as SchedulingState[];
      const query = (url.searchParams.get("query") ?? "").toLowerCase();
      const page = Number(url.searchParams.get("page") ?? "1");
      const filtered = state.issueItems.filter((item) =>
        (!selectedProjects.length || selectedProjects.includes(item.project_id)) &&
        (!selectedStates.length || selectedStates.includes(item.scheduling_state)) &&
        (!query || item.title.toLowerCase().includes(query)),
      );
      const response: IssuePage = {
        items: filtered,
        total: state.total ?? filtered.length,
        page,
        page_size: 25,
        by_state: countByState(
          state.issueItems.filter((item) =>
            !selectedProjects.length || selectedProjects.includes(item.project_id),
          ),
        ),
      };
      return jsonResponse(response);
    }
    return jsonResponse({ detail: `Unexpected request: ${url.pathname}` }, 500);
  });
  return state;
}

function latestIssueRequest(): URL {
  const call = [...fetchMock.mock.calls]
    .reverse()
    .find(([input]) => new URL(String(input)).pathname === "/issues");
  if (!call) throw new Error("No Issue request was made");
  return new URL(String(call[0]));
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function countByState(items: ManagedIssue[]): IssuePage["by_state"] {
  return Object.fromEntries(
    schedulingStates.map((state) => [
      state,
      items.filter((item) => item.scheduling_state === state).length,
    ]),
  );
}

function project(
  id: string,
  name: string,
  health: Project["sync"]["health"],
): Project {
  return {
    id,
    provider_repo_id: name,
    name,
    enabled: true,
    sync: {
      health,
      last_attempt_at: "2026-07-10T01:00:00Z",
      last_success_at: health === "healthy" ? "2026-07-10T01:00:00Z" : null,
      last_error: health === "error" ? "GitHub request failed" : null,
    },
  };
}

function issue(overrides: Partial<ManagedIssue>): ManagedIssue {
  return {
    id: "issue-1",
    project_id: "project-alpha",
    number: 1,
    title: "Issue",
    url: `https://github.com/acme/alpha/issues/${overrides.number ?? 1}`,
    source_state: "open",
    scheduling_state: "ready",
    scheduling_version: 1,
    analysis_version: 1,
    analysis_completed: true,
    manual_hold_reason: null,
    in_progress_since: null,
    source_updated_at: "2026-07-10T01:00:00Z",
    last_synced_at: "2026-07-10T01:00:00Z",
    dependencies: [],
    dependency_closed_count: 0,
    blocking_reasons: [],
    claimable_now: false,
    claim_block_reason: null,
    ...overrides,
  };
}
