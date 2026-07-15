import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  CircleDot,
  ExternalLink,
  FolderGit2,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import {
  API_BASE_URL,
  createProject,
  fetchHealth,
  fetchIssue,
  fetchIssues,
  fetchProjects,
  syncProject,
} from "./api";
import {
  schedulingStates,
  stateLabels,
  type IssuePage,
  type ManagedIssue,
  type Project,
  type RuntimeHealth,
  type SchedulingState,
} from "./domain";
import "./styles.css";

const PAGE_SIZE = 25;
const emptyIssuePage: IssuePage = {
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
  by_state: {},
};

type RequestState = "idle" | "loading" | "ready";

export function App() {
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [issues, setIssues] = useState<IssuePage>(emptyIssuePage);
  const [issuesError, setIssuesError] = useState<string | null>(null);
  const [issuesState, setIssuesState] = useState<RequestState>("idle");
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
  const [activeState, setActiveState] = useState<SchedulingState | null>(null);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [page, setPage] = useState(1);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<ManagedIssue | null>(null);
  const [detailState, setDetailState] = useState<RequestState>("idle");
  const [detailError, setDetailError] = useState<string | null>(null);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [addProjectOpen, setAddProjectOpen] = useState(false);
  const [syncingProjectIds, setSyncingProjectIds] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedProjectKey = selectedProjectIds.join("\u0000");

  useEffect(() => {
    const controller = new AbortController();
    void Promise.allSettled([
      fetchHealth(controller.signal).then((value) => {
        setHealth(value);
        setHealthError(null);
      }),
      fetchProjects(controller.signal).then((value) => {
        setProjects(value);
        setProjectsError(null);
      }),
    ]).then((results) => {
      if (controller.signal.aborted) {
        return;
      }
      const [healthResult, projectsResult] = results;
      if (healthResult.status === "rejected") {
        setHealth(null);
        setHealthError(errorMessage(healthResult.reason));
      }
      if (projectsResult.status === "rejected") {
        setProjects([]);
        setProjectsError(errorMessage(projectsResult.reason));
      }
    });
    return () => controller.abort();
  }, [refreshVersion]);

  useEffect(() => {
    const controller = new AbortController();
    setIssuesState("loading");
    void fetchIssues(
      {
        projectIds: selectedProjectIds,
        states: activeState ? [activeState] : [],
        query: deferredQuery,
        page,
        pageSize: PAGE_SIZE,
      },
      controller.signal,
    )
      .then((value) => {
        setIssues(value);
        setIssuesError(null);
        setLastRefreshAt(new Date().toISOString());
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setIssues(emptyIssuePage);
          setIssuesError(errorMessage(error));
          setLastRefreshAt(new Date().toISOString());
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIssuesState("ready");
        }
      });
    return () => controller.abort();
  }, [activeState, deferredQuery, page, refreshVersion, selectedProjectKey]);

  useEffect(() => {
    if (!selectedIssue) {
      setDetailState("idle");
      setDetailError(null);
      return;
    }
    const controller = new AbortController();
    setDetailState("loading");
    setDetailError(null);
    void fetchIssue(selectedIssue.id, controller.signal)
      .then(setSelectedIssue)
      .catch((error) => {
        if (!controller.signal.aborted) {
          setDetailError(errorMessage(error));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailState("ready");
        }
      });
    return () => controller.abort();
  }, [selectedIssue?.id]);

  const projectById = useMemo(
    () => new Map(projects.map((project) => [project.id, project])),
    [projects],
  );
  const totalPages = Math.max(1, Math.ceil(issues.total / issues.page_size));
  const allStateCount = sumStateCounts(issues) || issues.total;

  const selectState = useCallback((state: SchedulingState | null) => {
    setActiveState(state);
    setPage(1);
  }, []);

  const toggleProject = useCallback((projectId: string) => {
    setSelectedProjectIds((current) =>
      current.includes(projectId)
        ? current.filter((id) => id !== projectId)
        : [...current, projectId],
    );
    setPage(1);
  }, []);

  const refresh = useCallback(() => {
    setNotice(null);
    setRefreshVersion((value) => value + 1);
  }, []);

  const handleSync = useCallback(async (project: Project) => {
    setSyncingProjectIds((current) => [...current, project.id]);
    setNotice(null);
    try {
      await syncProject(project.id);
      setNotice(`${project.name} synchronized.`);
      setRefreshVersion((value) => value + 1);
    } catch (error) {
      setNotice(`Sync failed: ${errorMessage(error)}`);
    } finally {
      setSyncingProjectIds((current) => current.filter((id) => id !== project.id));
    }
  }, []);

  const handleProjectCreated = useCallback((project: Project) => {
    setAddProjectOpen(false);
    setSelectedProjectIds([project.id]);
    setPage(1);
    setRefreshVersion((value) => value + 1);
    void handleSync(project);
  }, [handleSync]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">K</span>
          <div>
            <strong>Kairota</strong>
            <span>Issue scheduling</span>
          </div>
        </div>
        <div className="topbar-actions">
          <ConnectionStatus error={healthError} health={health} />
          <button
            aria-label="Refresh data"
            className="icon-button icon-button--quiet"
            disabled={issuesState === "loading"}
            onClick={refresh}
            title="Refresh data"
            type="button"
          >
            <RefreshCw
              aria-hidden="true"
              className={issuesState === "loading" ? "spin" : undefined}
              size={17}
            />
          </button>
          <button
            className="command-button"
            onClick={() => setAddProjectOpen(true)}
            type="button"
          >
            <Plus aria-hidden="true" size={17} />
            Add project
          </button>
        </div>
      </header>

      <section className="workspace" aria-label="GitHub Issue scheduling board">
        <div className="workspace-heading">
          <div>
            <h1>Issues</h1>
            <p>
              {issues.total} matching {issues.total === 1 ? "issue" : "issues"}
              {lastRefreshAt ? ` | Updated ${formatRelative(lastRefreshAt)}` : ""}
            </p>
          </div>
          <div className="filters">
            <ProjectPicker
              error={projectsError}
              onClear={() => {
                setSelectedProjectIds([]);
                setPage(1);
              }}
              onOpenChange={setProjectPickerOpen}
              onSync={handleSync}
              onToggle={toggleProject}
              open={projectPickerOpen}
              projects={projects}
              selectedIds={selectedProjectIds}
              syncingIds={syncingProjectIds}
            />
            <label className="search-field">
              <Search aria-hidden="true" size={16} />
              <input
                aria-label="Search issues"
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(1);
                }}
                placeholder="Search issues"
                value={query}
              />
              {query ? (
                <button
                  aria-label="Clear search"
                  onClick={() => {
                    setQuery("");
                    setPage(1);
                  }}
                  title="Clear search"
                  type="button"
                >
                  <X aria-hidden="true" size={15} />
                </button>
              ) : null}
            </label>
          </div>
        </div>

        <StatusFilter
          activeState={activeState}
          allCount={allStateCount}
          byState={issues.by_state}
          onSelect={selectState}
        />

        {notice ? (
          <div className="notice" role="status">
            {notice}
            <button
              aria-label="Dismiss notification"
              onClick={() => setNotice(null)}
              title="Dismiss"
              type="button"
            >
              <X aria-hidden="true" size={15} />
            </button>
          </div>
        ) : null}

        <div className={`content-layout${selectedIssue ? " content-layout--detail" : ""}`}>
          <section className="issue-surface" aria-label="Issues">
            {issuesError ? (
              <ErrorState message={issuesError} onRetry={refresh} />
            ) : issuesState === "loading" && issues.items.length === 0 ? (
              <LoadingState />
            ) : issues.items.length === 0 ? (
              <EmptyState hasFilters={Boolean(activeState || query || selectedProjectIds.length)} />
            ) : (
              <IssueTable
                issues={issues.items}
                onSelect={setSelectedIssue}
                projectById={projectById}
                selectedIssueId={selectedIssue?.id ?? null}
              />
            )}
            {!issuesError && issues.total > 0 ? (
              <Pagination
                currentPage={issues.page}
                onPageChange={setPage}
                pageSize={issues.page_size}
                total={issues.total}
                totalPages={totalPages}
              />
            ) : null}
          </section>

          {selectedIssue ? (
            <IssueDetail
              error={detailError}
              issue={selectedIssue}
              loading={detailState === "loading"}
              onClose={() => setSelectedIssue(null)}
              project={projectById.get(selectedIssue.project_id)}
            />
          ) : null}
        </div>
      </section>

      {addProjectOpen ? (
        <AddProjectDialog
          onClose={() => setAddProjectOpen(false)}
          onCreated={handleProjectCreated}
        />
      ) : null}
    </main>
  );
}

function ConnectionStatus({
  error,
  health,
}: {
  error: string | null;
  health: RuntimeHealth | null;
}) {
  const connected = health?.status === "ok" && !error;
  return (
    <div
      className={`connection-status connection-status--${connected ? "online" : "offline"}`}
      title={connected ? `${health.service} ${health.version} | ${API_BASE_URL}` : error ?? API_BASE_URL}
    >
      <span aria-hidden="true" />
      {connected ? "Connected" : "Disconnected"}
    </div>
  );
}

function ProjectPicker({
  error,
  onClear,
  onOpenChange,
  onSync,
  onToggle,
  open,
  projects,
  selectedIds,
  syncingIds,
}: {
  error: string | null;
  onClear: () => void;
  onOpenChange: (open: boolean) => void;
  onSync: (project: Project) => void;
  onToggle: (projectId: string) => void;
  open: boolean;
  projects: Project[];
  selectedIds: string[];
  syncingIds: string[];
}) {
  const [projectQuery, setProjectQuery] = useState("");
  const pickerRef = useRef<HTMLDivElement>(null);
  const normalizedQuery = projectQuery.trim().toLowerCase();
  const visibleProjects = normalizedQuery
    ? projects.filter((project) => project.name.toLowerCase().includes(normalizedQuery))
    : projects;
  const selected = new Set(selectedIds);
  const syncing = new Set(syncingIds);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsidePointer(event: PointerEvent) {
      if (!pickerRef.current?.contains(event.target as Node)) onOpenChange(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [onOpenChange, open]);

  return (
    <div className="project-picker" aria-label="Project filter" ref={pickerRef}>
      <button
        aria-expanded={open}
        className={`filter-button${selectedIds.length ? " filter-button--active" : ""}`}
        onClick={() => onOpenChange(!open)}
        type="button"
      >
        <FolderGit2 aria-hidden="true" size={16} />
        <span>{selectedIds.length ? `${selectedIds.length} selected` : "All projects"}</span>
        <ChevronsUpDown aria-hidden="true" size={14} />
      </button>
      {open ? (
        <div className="project-menu">
          <div className="project-menu__header">
            <strong>Projects</strong>
            <span>{selectedIds.length ? `${selectedIds.length} selected` : "All selected"}</span>
          </div>
          {projects.length > 6 ? (
            <label className="project-search">
              <Search aria-hidden="true" size={15} />
              <input
                aria-label="Search projects"
                autoFocus
                onChange={(event) => setProjectQuery(event.target.value)}
                placeholder="Find a project"
                value={projectQuery}
              />
            </label>
          ) : null}
          <button
            aria-pressed={selectedIds.length === 0}
            className="project-all"
            onClick={onClear}
            type="button"
          >
            <span className="checkbox-indicator" aria-hidden="true">
              {selectedIds.length === 0 ? <Check size={14} /> : null}
            </span>
            <span>All projects</span>
          </button>
          <div className="project-options">
            {visibleProjects.map((project) => (
              <div className="project-option" key={project.id}>
                <label>
                  <input
                    checked={selected.has(project.id)}
                    onChange={() => onToggle(project.id)}
                    type="checkbox"
                  />
                  <span className="checkbox-indicator" aria-hidden="true">
                    {selected.has(project.id) ? <Check size={14} /> : null}
                  </span>
                  <span className="project-option__label">
                    <strong>{project.name}</strong>
                    <small>
                      <span className={`sync-dot sync-dot--${project.sync.health}`} />
                      {syncLabel(project)}
                    </small>
                  </span>
                </label>
                <button
                  aria-label={`Sync ${project.name}`}
                  className="menu-icon-button"
                  disabled={syncing.has(project.id)}
                  onClick={() => onSync(project)}
                  title={`Sync ${project.name}`}
                  type="button"
                >
                  <RefreshCw
                    aria-hidden="true"
                    className={syncing.has(project.id) ? "spin" : undefined}
                    size={15}
                  />
                </button>
              </div>
            ))}
            {visibleProjects.length === 0 ? (
              <p className="project-menu__empty">
                {error ?? (projects.length ? "No matching projects" : "No projects registered")}
              </p>
            ) : null}
          </div>
          <div className="project-menu__footer">
            <button disabled={selectedIds.length === 0} onClick={onClear} type="button">
              Clear selection
            </button>
            <button onClick={() => onOpenChange(false)} type="button">Done</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StatusFilter({
  activeState,
  allCount,
  byState,
  onSelect,
}: {
  activeState: SchedulingState | null;
  allCount: number;
  byState: IssuePage["by_state"];
  onSelect: (state: SchedulingState | null) => void;
}) {
  return (
    <nav className="status-filter" aria-label="Issue status">
      <button
        aria-pressed={activeState === null}
        className={activeState === null ? "status-filter__item status-filter__item--active" : "status-filter__item"}
        onClick={() => onSelect(null)}
        type="button"
      >
        <span>All</span>
        <strong>{allCount}</strong>
      </button>
      {schedulingStates.map((state) => (
        <button
          aria-pressed={activeState === state}
          className={`status-filter__item status-filter__item--${state}${activeState === state ? " status-filter__item--active" : ""}`}
          key={state}
          onClick={() => onSelect(state)}
          type="button"
        >
          <span>{stateLabels[state]}</span>
          <strong>{byState[state] ?? 0}</strong>
        </button>
      ))}
    </nav>
  );
}

function IssueTable({
  issues,
  onSelect,
  projectById,
  selectedIssueId,
}: {
  issues: ManagedIssue[];
  onSelect: (issue: ManagedIssue) => void;
  projectById: Map<string, Project>;
  selectedIssueId: string | null;
}) {
  return (
    <div className="table-scroll">
      <table className="issue-table">
        <thead>
          <tr>
            <th>Project</th>
            <th>Issue</th>
            <th>Status</th>
            <th>Dependencies</th>
            <th>Scheduling fact</th>
            <th>Last synced</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue) => {
            const project = projectById.get(issue.project_id);
            return (
              <tr
                aria-selected={selectedIssueId === issue.id}
                className={selectedIssueId === issue.id ? "issue-row issue-row--selected" : "issue-row"}
                key={issue.id}
                onClick={() => onSelect(issue)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(issue);
                  }
                }}
                tabIndex={0}
              >
                <td data-label="Project">
                  <span className="project-name" title={project?.name ?? issue.project_id}>
                    {project?.name ?? "Unknown project"}
                  </span>
                </td>
                <td data-label="Issue">
                  <button className="issue-title" onClick={() => onSelect(issue)} type="button">
                    <span>#{issue.number}</span>
                    <strong>{issue.title}</strong>
                  </button>
                </td>
                <td data-label="Status"><StatusBadge state={issue.scheduling_state} /></td>
                <td data-label="Dependencies"><DependencyProgress issue={issue} /></td>
                <td data-label="Scheduling fact">
                  <span className="scheduling-fact">{schedulingFact(issue)}</span>
                </td>
                <td data-label="Last synced">
                  <time className="sync-time" dateTime={issue.last_synced_at ?? undefined} title={formatTimestamp(issue.last_synced_at)}>
                    {formatRelative(issue.last_synced_at)}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ state }: { state: SchedulingState }) {
  return (
    <span className={`status-badge status-badge--${state}`}>
      <span aria-hidden="true" />
      {stateLabels[state]}
    </span>
  );
}

function DependencyProgress({ issue }: { issue: ManagedIssue }) {
  if (!issue.analysis_completed) {
    return <span className="dependency-empty">Not analyzed</span>;
  }
  if (issue.dependencies.length === 0) {
    return <span className="dependency-empty">None</span>;
  }
  const ratio = issue.dependency_closed_count / issue.dependencies.length;
  return (
    <div className="dependency-progress" title={`${issue.dependency_closed_count} of ${issue.dependencies.length} dependencies closed`}>
      <span>{issue.dependency_closed_count}/{issue.dependencies.length} closed</span>
      <span className="progress-track" aria-hidden="true">
        <span style={{ width: `${Math.min(100, ratio * 100)}%` }} />
      </span>
    </div>
  );
}

function IssueDetail({
  error,
  issue,
  loading,
  onClose,
  project,
}: {
  error: string | null;
  issue: ManagedIssue;
  loading: boolean;
  onClose: () => void;
  project: Project | undefined;
}) {
  return (
    <aside className="detail-panel" aria-label="Issue details">
      <header className="detail-panel__header">
        <div>
          <span>{project?.name ?? "Unknown project"} | #{issue.number}</span>
          <h2>{issue.title}</h2>
        </div>
        <button aria-label="Close issue details" onClick={onClose} title="Close details" type="button">
          <X aria-hidden="true" size={18} />
        </button>
      </header>
      {loading ? <div className="detail-loading"><LoaderCircle className="spin" size={16} /> Refreshing facts</div> : null}
      {error ? <p className="detail-error" role="alert">Could not refresh details: {error}</p> : null}
      <div className="detail-actions">
        <a href={issue.url} rel="noreferrer" target="_blank">
          Open on GitHub <ExternalLink aria-hidden="true" size={14} />
        </a>
      </div>
      <section className="detail-section">
        <h3>Scheduling</h3>
        <dl className="fact-list">
          <div><dt>Status</dt><dd><StatusBadge state={issue.scheduling_state} /></dd></div>
          <div><dt>GitHub state</dt><dd className="capitalize">{issue.source_state}</dd></div>
          <div><dt>Dependency analysis</dt><dd>{issue.analysis_completed ? "Complete" : "Required"}</dd></div>
          <div><dt>Dependencies closed</dt><dd>{issue.dependency_closed_count} of {issue.dependencies.length}</dd></div>
          {issue.in_progress_since ? <div><dt>In progress since</dt><dd>{formatTimestamp(issue.in_progress_since)}</dd></div> : null}
        </dl>
      </section>
      {issue.manual_hold_reason || issue.blocking_reasons.length ? (
        <section className="detail-section">
          <h3>Blocking facts</h3>
          <ul className="fact-notes">
            {issue.manual_hold_reason ? <li>{issue.manual_hold_reason}</li> : null}
            {issue.blocking_reasons.map((reason) => <li key={reason}>{humanizeReason(reason)}</li>)}
          </ul>
        </section>
      ) : null}
      <section className="detail-section">
        <h3>Dependencies</h3>
        {issue.dependencies.length ? (
          <ul className="dependency-list">
            {issue.dependencies.map((dependency) => (
              <li key={dependency.issue_id}>
                <span className={`source-dot source-dot--${dependency.source_state}`} aria-hidden="true" />
                <a href={dependency.url} rel="noreferrer" target="_blank">
                  <span>#{dependency.number}</span>
                  <strong>{dependency.title}</strong>
                  <ExternalLink aria-hidden="true" size={13} />
                </a>
                <small className="capitalize">{dependency.source_state}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="detail-muted">{issue.analysis_completed ? "No dependencies." : "Dependency analysis has not been reported."}</p>
        )}
      </section>
      <section className="detail-section">
        <h3>Synchronization</h3>
        <dl className="fact-list">
          <div><dt>Issue synchronized</dt><dd>{formatTimestamp(issue.last_synced_at)}</dd></div>
          <div><dt>Project health</dt><dd><SyncHealthLabel project={project} /></dd></div>
          {project?.sync.last_success_at ? <div><dt>Project last success</dt><dd>{formatTimestamp(project.sync.last_success_at)}</dd></div> : null}
          {project?.sync.last_error ? <div><dt>Latest sync error</dt><dd className="error-text">{project.sync.last_error}</dd></div> : null}
        </dl>
      </section>
    </aside>
  );
}

function SyncHealthLabel({ project }: { project: Project | undefined }) {
  if (!project) {
    return <>Unknown</>;
  }
  return <span className="sync-health"><span className={`sync-dot sync-dot--${project.sync.health}`} />{project.sync.health}</span>;
}

function Pagination({
  currentPage,
  onPageChange,
  pageSize,
  total,
  totalPages,
}: {
  currentPage: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  total: number;
  totalPages: number;
}) {
  const first = (currentPage - 1) * pageSize + 1;
  const last = Math.min(currentPage * pageSize, total);
  return (
    <nav className="pagination" aria-label="Issue pages">
      <span>{first}-{last} of {total}</span>
      <div>
        <button aria-label="Previous page" disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} title="Previous page" type="button">
          <ChevronLeft aria-hidden="true" size={17} />
        </button>
        <span>Page {currentPage} of {totalPages}</span>
        <button aria-label="Next page" disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)} title="Next page" type="button">
          <ChevronRight aria-hidden="true" size={17} />
        </button>
      </div>
    </nav>
  );
}

function AddProjectDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (project: Project) => void;
}) {
  const [remote, setRemote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !submitting) onClose();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose, submitting]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!remote.trim()) {
      setError("Enter a GitHub repository URL or owner/name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      onCreated(await createProject(remote.trim()));
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <section aria-labelledby="add-project-title" aria-modal="true" className="dialog" role="dialog">
        <header>
          <div>
            <h2 id="add-project-title">Add project</h2>
            <p>Register a GitHub repository for Issue synchronization.</p>
          </div>
          <button aria-label="Close add project" onClick={onClose} title="Close" type="button"><X aria-hidden="true" size={18} /></button>
        </header>
        <form aria-label="Add project" onSubmit={submit}>
          <label>
            GitHub repository
            <input
              autoFocus
              disabled={submitting}
              onChange={(event) => setRemote(event.target.value)}
              placeholder="owner/repository"
              value={remote}
            />
          </label>
          <p className="field-help">GitHub HTTPS URLs and owner/repository names are accepted.</p>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <footer>
            <button className="secondary-button" disabled={submitting} onClick={onClose} type="button">Cancel</button>
            <button className="command-button" disabled={submitting} type="submit">
              {submitting ? <LoaderCircle aria-hidden="true" className="spin" size={16} /> : <Plus aria-hidden="true" size={16} />}
              Add project
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function LoadingState() {
  return <div className="state-message" role="status"><LoaderCircle className="spin" size={20} /><strong>Loading Issues</strong><span>Reading the current scheduler view.</span></div>;
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return <div className="state-message"><CircleDot size={20} /><strong>{hasFilters ? "No matching Issues" : "No Issues synchronized"}</strong><span>{hasFilters ? "Change the project, status, or search filter." : "Add a project or synchronize a registered project."}</span></div>;
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="state-message state-message--error" role="alert"><AlertCircle size={20} /><strong>Issues could not be loaded</strong><span>{message}</span><button className="secondary-button" onClick={onRetry} type="button">Try again</button></div>;
}

function schedulingFact(issue: ManagedIssue): string {
  if (issue.manual_hold_reason) return issue.manual_hold_reason;
  if (issue.blocking_reasons.length) return humanizeReason(issue.blocking_reasons[0]);
  if (issue.scheduling_state === "needs_analysis") return "Dependency analysis required";
  if (issue.scheduling_state === "ready") return "Dependencies satisfied";
  if (issue.scheduling_state === "in_progress") return "Assigned by main AI";
  if (issue.scheduling_state === "closed") return "GitHub Issue closed";
  return issue.claim_block_reason ? humanizeReason(issue.claim_block_reason) : "Waiting for dependencies";
}

function humanizeReason(reason: string): string {
  if (reason.startsWith("dependency_open:")) {
    return `Dependency Issue #${reason.split(":", 2)[1]} is open`;
  }
  const labels: Record<string, string> = {
    analysis_required: "Dependency analysis is required",
    manual_hold: "Manual hold",
    project_disabled: "Project scheduling is disabled",
    sync_unhealthy: "Project synchronization is unhealthy",
    sync_unknown: "Project has not synchronized successfully",
    sync_stale: "Project synchronization is stale",
  };
  if (labels[reason]) return labels[reason];
  return reason.replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

function syncLabel(project: Project): string {
  if (project.sync.health === "syncing") return "Synchronizing";
  if (project.sync.last_success_at) return `${project.sync.health} | ${formatRelative(project.sync.last_success_at)}`;
  return project.sync.health;
}

function sumStateCounts(page: IssuePage): number {
  return schedulingStates.reduce((total, state) => total + (page.by_state[state] ?? 0), 0);
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatRelative(value: string | null | undefined): string {
  if (!value) return "Never";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Unknown";
  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const absoluteSeconds = Math.abs(seconds);
  if (absoluteSeconds < 60) return "just now";
  if (absoluteSeconds < 3600) return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(seconds / 60), "minute");
  if (absoluteSeconds < 86400) return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(seconds / 3600), "hour");
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(seconds / 86400), "day");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}
