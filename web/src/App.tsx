import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clock3,
  GitPullRequest,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";

import {
  fetchQueueWorkbench,
  fetchRepositories,
  fetchRuntimeHealth,
  getApiBaseUrl,
} from "./api";
import "./styles.css";
import {
  allRows,
  emptyWorkbench,
  sectionTones,
  type Repository,
  type QueueWorkbench,
  type QueueWorkbenchEvent,
  type QueueWorkbenchRecoverySignal,
  type QueueWorkbenchRow,
  type QueueWorkbenchSection,
  type RuntimeHealth,
  type SectionId,
} from "./workbench";

type DataSource = "api" | "empty";
type LoadState = "idle" | "loading" | "ready";

const sectionIcons: Record<SectionId, typeof CircleDot> = {
  ready: CircleDot,
  running: Activity,
  blocked: ShieldAlert,
  waiting: Clock3,
  failed: AlertTriangle,
  done: CheckCircle2,
};

const allSections = "all";
const unscopedProjectId = "__unscoped__";

type ProjectFilterOption = {
  id: string;
  label: string;
  count: number;
  syncStatus: string | null;
};

export function App() {
  const [workbench, setWorkbench] = useState<QueueWorkbench>(emptyWorkbench);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoriesError, setRepositoriesError] = useState<string | null>(null);
  const [source, setSource] = useState<DataSource>("empty");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<SectionId | typeof allSections>(
    allSections,
  );
  const [query, setQuery] = useState("");
  const [selectedRepositoryIds, setSelectedRepositoryIds] = useState<string[]>([]);
  const [selectedRowId, setSelectedRowId] = useState<string>("");
  const apiBaseUrl = useMemo(() => getApiBaseUrl(), []);

  const loadWorkbench = useCallback(async (signal?: AbortSignal) => {
    setLoadState("loading");
    try {
      const [data, runtime, repositoryResult] = await Promise.all([
        fetchQueueWorkbench(signal),
        fetchRuntimeHealth(signal)
          .then((value) => ({ value, error: null }))
          .catch((error) => ({
            value: null,
            error: error instanceof Error ? error.message : "Health request failed",
          })),
        fetchRepositories(signal)
          .then((value) => ({ value, error: null }))
          .catch((error) => ({
            value: [] as Repository[],
            error:
              error instanceof Error ? error.message : "Repositories request failed",
          })),
      ]);
      setWorkbench(data);
      setRepositories(repositoryResult.value);
      setRepositoriesError(repositoryResult.error);
      setSource("api");
      setLoadError(null);
      setHealth(runtime.value);
      setHealthError(runtime.error);
      setLastRefreshAt(new Date().toISOString());
      setSelectedRowId((current) => current || allRows(data)[0]?.id || "");
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setWorkbench(emptyWorkbench);
      setRepositories([]);
      setRepositoriesError(null);
      setSource("empty");
      setLoadError(error instanceof Error ? error.message : "Request failed");
      setHealth(null);
      setHealthError(null);
      setLastRefreshAt(new Date().toISOString());
      setSelectedRowId("");
    } finally {
      if (!signal?.aborted) {
        setLoadState("ready");
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadWorkbench(controller.signal);
    return () => controller.abort();
  }, [loadWorkbench]);

  const rows = useMemo(() => allRows(workbench), [workbench]);
  const rowsById = useMemo(
    () => new Map(rows.map((row) => [row.id, row])),
    [rows],
  );
  const repositoryById = useMemo(
    () => new Map(repositories.map((repository) => [repository.id, repository])),
    [repositories],
  );
  const searchMatchedRows = useMemo(() => filterRows(rows, query, []), [query, rows]);
  const projectOptions = useMemo(
    () => buildProjectOptions(searchMatchedRows, repositories),
    [repositories, searchMatchedRows],
  );
  const navSections = useMemo(
    () =>
      filterSections(workbench.sections, allSections, query, selectedRepositoryIds),
    [query, selectedRepositoryIds, workbench.sections],
  );
  const filteredSections = useMemo(
    () =>
      filterSections(workbench.sections, activeSection, query, selectedRepositoryIds),
    [activeSection, query, selectedRepositoryIds, workbench.sections],
  );
  const navRows = useMemo(() => rowsFromSections(navSections), [navSections]);
  const visibleRows = useMemo(
    () => rowsFromSections(filteredSections),
    [filteredSections],
  );
  const decisionRows = useMemo(
    () => filterRows(workbench.decision_inbox, query, selectedRepositoryIds),
    [query, selectedRepositoryIds, workbench.decision_inbox],
  );
  const selectedRow =
    visibleRows.find((row) => row.id === selectedRowId) ?? visibleRows[0] ?? null;
  const totalSuffix =
    visibleRows.length === rows.length ? "" : ` (${rows.length} total)`;
  const toggleRepository = useCallback((repositoryId: string) => {
    setSelectedRepositoryIds((current) =>
      current.includes(repositoryId)
        ? current.filter((id) => id !== repositoryId)
        : [...current, repositoryId],
    );
  }, []);

  return (
    <main className="app-shell">
      <aside className="side-rail" aria-label="Queue navigation">
        <div className="brand-lockup">
          <span className="brand-mark">K</span>
          <div>
            <strong>Kairota</strong>
            <span>AI Dev Queue</span>
          </div>
        </div>
        <nav className="section-nav" aria-label="Queue sections">
          <NavButton
            active={activeSection === allSections}
            count={navRows.length}
            label="All"
            onClick={() => setActiveSection(allSections)}
          />
          {navSections.map((section) => (
            <NavButton
              active={activeSection === section.id}
              count={section.count}
              key={section.id}
              label={section.title}
              onClick={() => setActiveSection(section.id)}
              sectionId={section.id}
            />
          ))}
        </nav>
      </aside>

      <section className="workspace" aria-label="Queue workbench">
        <header className="command-bar">
          <div>
            <h1>AI Dev Queue</h1>
            <p className="bar-copy">
              {source === "api" ? "Local API" : "No API data"} -{" "}
              {visibleRows.length} visible work items{totalSuffix}
            </p>
          </div>
          <div className="command-actions">
            <label className="search-box">
              <Search aria-hidden="true" size={16} />
              <input
                aria-label="Search work items"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search title, status, reason"
                value={query}
              />
            </label>
            <button
              className="icon-button"
              disabled={loadState === "loading"}
              onClick={() => void loadWorkbench()}
              type="button"
            >
              <RefreshCw aria-hidden="true" size={16} />
              Refresh
            </button>
          </div>
        </header>

        <ProjectFilter
          allCount={searchMatchedRows.length}
          error={repositoriesError}
          onClear={() => setSelectedRepositoryIds([])}
          onToggle={toggleRepository}
          options={projectOptions}
          selectedRepositoryIds={selectedRepositoryIds}
        />

        <SummaryStrip
          decisionCount={decisionRows.length}
          failureCount={workbench.failures.length}
          summary={workbench.summary}
          visibleCount={visibleRows.length}
        />

        <RuntimeStatus
          apiBaseUrl={apiBaseUrl}
          health={health}
          healthError={healthError}
          lastRefreshAt={lastRefreshAt}
          loadState={loadState}
        />

        {loadError ? (
          <div className="runtime-note" role="status">
            API unavailable - {loadError}
          </div>
        ) : null}

        <div className="workbench-layout">
          <section className="queue-board" aria-label="Queue status sections">
            {filteredSections.map((section) => (
              <QueueSection
                key={section.id}
                onSelect={setSelectedRowId}
                repositoryById={repositoryById}
                section={section}
                selectedRowId={selectedRow?.id ?? ""}
              />
            ))}
          </section>

          <aside className="detail-rail" aria-label="Work item details">
            {selectedRow ? (
              <DetailPanel
                repositoryById={repositoryById}
                row={selectedRow}
                rowsById={rowsById}
              />
            ) : (
              <EmptyDetail />
            )}
            <DecisionInbox
              onSelect={setSelectedRowId}
              repositoryById={repositoryById}
              rows={decisionRows}
              selectedRowId={selectedRow?.id ?? ""}
            />
            <RecoverySignals signals={workbench.recovery_signals} />
            <EventFeed events={workbench.failures} title="Failures" />
            <EventFeed events={workbench.recent_events} title="Recent Events" />
          </aside>
        </div>
      </section>
    </main>
  );
}

function RuntimeStatus({
  apiBaseUrl,
  health,
  healthError,
  lastRefreshAt,
  loadState,
}: {
  apiBaseUrl: string;
  health: RuntimeHealth | null;
  healthError: string | null;
  lastRefreshAt: string | null;
  loadState: LoadState;
}) {
  const cells = [
    ["API Base", apiBaseUrl],
    ["Health", health ? `${health.service} ${health.version}` : healthError ?? "unknown"],
    ["Database", health?.database_identity ?? "unknown"],
    ["Refresh", loadState === "loading" ? "loading" : formatDate(lastRefreshAt)],
  ];
  return (
    <section className="runtime-panel" aria-label="Runtime status">
      {cells.map(([label, value]) => (
        <div className="runtime-cell" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

function ProjectFilter({
  allCount,
  error,
  onClear,
  onToggle,
  options,
  selectedRepositoryIds,
}: {
  allCount: number;
  error: string | null;
  onClear: () => void;
  onToggle: (repositoryId: string) => void;
  options: ProjectFilterOption[];
  selectedRepositoryIds: string[];
}) {
  const selected = new Set(selectedRepositoryIds);
  return (
    <section className="project-filter" aria-label="Project filter">
      <div className="project-filter__heading">
        <span>Projects</span>
        <strong>
          {selectedRepositoryIds.length > 0
            ? `${selectedRepositoryIds.length} selected`
            : "All projects"}
        </strong>
      </div>
      <div className="project-filter__options">
        <button
          aria-pressed={selectedRepositoryIds.length === 0}
          className={`filter-chip${
            selectedRepositoryIds.length === 0 ? " filter-chip--active" : ""
          }`}
          onClick={onClear}
          type="button"
        >
          <span className="filter-chip__main">All</span>
          <strong>{allCount}</strong>
        </button>
        {options.map((option) => (
          <button
            aria-pressed={selected.has(option.id)}
            className={`filter-chip${selected.has(option.id) ? " filter-chip--active" : ""}`}
            key={option.id}
            onClick={() => onToggle(option.id)}
            type="button"
          >
            <span className="filter-chip__main">{option.label}</span>
            {option.syncStatus ? (
              <span className="filter-chip__meta">{option.syncStatus}</span>
            ) : null}
            <strong>{option.count}</strong>
          </button>
        ))}
      </div>
      {error ? (
        <p className="project-filter__error" role="status">
          Project list unavailable - {error}
        </p>
      ) : null}
    </section>
  );
}

function SummaryStrip({
  decisionCount,
  failureCount,
  summary,
  visibleCount,
}: {
  decisionCount: number;
  failureCount: number;
  summary: QueueWorkbench["summary"];
  visibleCount: number;
}) {
  const metrics = [
    ["Visible", visibleCount],
    ["Active leases", summary.active_leases],
    ["Active locks", summary.active_locks],
    ["Decisions", decisionCount],
    ["Failures", failureCount],
  ];
  return (
    <section className="summary-strip" aria-label="Queue summary">
      {metrics.map(([label, value]) => (
        <div className="summary-cell" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

function NavButton({
  active,
  count,
  label,
  onClick,
  sectionId,
}: {
  active: boolean;
  count: number;
  label: string;
  onClick: () => void;
  sectionId?: SectionId;
}) {
  const Icon = sectionId ? sectionIcons[sectionId] : CircleDot;
  return (
    <button
      className={`nav-item${active ? " nav-item--active" : ""}`}
      onClick={onClick}
      type="button"
    >
      <Icon aria-hidden="true" size={16} />
      <span>{label}</span>
      <strong>{count}</strong>
    </button>
  );
}

function QueueSection({
  onSelect,
  repositoryById,
  section,
  selectedRowId,
}: {
  onSelect: (rowId: string) => void;
  repositoryById: Map<string, Repository>;
  section: QueueWorkbenchSection;
  selectedRowId: string;
}) {
  const Icon = sectionIcons[section.id];
  return (
    <section className="queue-section" aria-labelledby={`${section.id}-heading`}>
      <header className="queue-section__header">
        <div>
          <Icon aria-hidden="true" size={18} />
          <h2 id={`${section.id}-heading`}>{section.title}</h2>
        </div>
        <span className={`count-badge count-badge--${sectionTones[section.id]}`}>
          {section.count}
        </span>
      </header>
      <div className="queue-section__rows">
        {section.rows.length > 0 ? (
          section.rows.map((row) => (
            <WorkRow
              key={row.id}
              onSelect={onSelect}
              repositoryById={repositoryById}
              row={row}
              selected={row.id === selectedRowId}
            />
          ))
        ) : (
          <p className="empty-state">No work</p>
        )}
      </div>
    </section>
  );
}

function WorkRow({
  onSelect,
  repositoryById,
  row,
  selected,
}: {
  onSelect: (rowId: string) => void;
  repositoryById: Map<string, Repository>;
  row: QueueWorkbenchRow;
  selected: boolean;
}) {
  const projectLabel = repositoryLabel(row.repository_id, repositoryById);
  return (
    <button
      className={`work-row${selected ? " work-row--selected" : ""}`}
      onClick={() => onSelect(row.id)}
      type="button"
    >
      <span className="work-row__title">{row.title}</span>
      <span className="work-row__project" title={projectLabel}>
        {projectLabel}
      </span>
      <span className="work-row__meta">
        P{row.priority} - {row.risk} - {row.work_type}
      </span>
      <span className="work-row__reason">{row.reason_code}</span>
      <span className="work-row__action">{row.next_action}</span>
    </button>
  );
}

function DetailPanel({
  repositoryById,
  row,
  rowsById,
}: {
  repositoryById: Map<string, Repository>;
  row: QueueWorkbenchRow;
  rowsById: Map<string, QueueWorkbenchRow>;
}) {
  const repository = row.repository;
  const projectLabel = repositoryLabel(row.repository_id, repositoryById);
  return (
    <section className="detail-panel" aria-label="Selected work item">
      <div className="detail-panel__title">
        <span className={`status-dot status-dot--${sectionTones[row.section]}`} />
        <h2>{row.title}</h2>
      </div>
      <div className="detail-grid">
        <DetailFact label="Status" value={row.status} />
        <DetailFact label="Priority" value={`P${row.priority}`} />
        <DetailFact label="Risk" value={row.risk} />
        <DetailFact label="Type" value={row.work_type} />
        <DetailFact label="Project" value={projectLabel} />
      </div>
      <DetailText label="Source" value={row.source_url ?? "not linked"} />
      <DetailText label="Reason" value={row.reason_code} />
      <DetailText label="Next Action" value={row.next_action} />
      <DetailText label="Expected Touch" value={row.expected_touch ?? "not set"} />
      <DetailText label="Acceptance" value={row.acceptance ?? "not set"} />
      <DetailText label="Validation" value={row.validation ?? "not set"} />
      <TagGroup label="Conflicts" values={row.conflict_keys} />
      <DependencyGroup dependencyIds={row.dependency_ids} rowsById={rowsById} />
      {row.worker_run ? <WorkerRunSummary run={row.worker_run} /> : null}
      {Object.keys(repository).length > 0 ? (
        <RepositorySummary repository={repository} />
      ) : null}
    </section>
  );
}

function DetailFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DetailText({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-text">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}

function TagGroup({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="tag-group">
      <span>{label}</span>
      <div>
        {values.length > 0 ? (
          values.map((value) => <code key={value}>{value}</code>)
        ) : (
          <em>none</em>
        )}
      </div>
    </div>
  );
}

function DependencyGroup({
  dependencyIds,
  rowsById,
}: {
  dependencyIds: string[];
  rowsById: Map<string, QueueWorkbenchRow>;
}) {
  const values = dependencyIds.map((dependencyId) => {
    const row = rowsById.get(dependencyId);
    return row ? `${row.title} - ${row.status}` : dependencyId;
  });
  return <TagGroup label="Dependencies" values={values} />;
}

function WorkerRunSummary({ run }: { run: NonNullable<QueueWorkbenchRow["worker_run"]> }) {
  return (
    <section className="inline-summary" aria-label="Worker run">
      <h3>Worker Run</h3>
      <DetailText label="Status" value={run.status} />
      <DetailText label="Role" value={run.role} />
      <DetailText label="Result" value={run.result ?? "open"} />
      <DetailText label="Heartbeat" value={formatDate(run.heartbeat_at)} />
    </section>
  );
}

function RepositorySummary({
  repository,
}: {
  repository: Record<string, unknown>;
}) {
  return (
    <section className="inline-summary" aria-label="Repository summary">
      <h3>
        <GitPullRequest aria-hidden="true" size={15} />
        Repository
      </h3>
      <DetailText
        label="PR"
        value={stringValue(repository.pull_request_number, "not linked")}
      />
      <DetailText
        label="Checks"
        value={`${stringValue(repository.pending_checks, "0")} pending - ${stringValue(
          repository.failing_checks,
          "0",
        )} failing`}
      />
      <DetailText
        label="Review"
        value={`${stringValue(repository.review_state, "unknown")} - ${stringValue(
          repository.unresolved_threads,
          "0",
        )} unresolved`}
      />
    </section>
  );
}

function DecisionInbox({
  onSelect,
  repositoryById,
  rows,
  selectedRowId,
}: {
  onSelect: (rowId: string) => void;
  repositoryById: Map<string, Repository>;
  rows: QueueWorkbenchRow[];
  selectedRowId: string;
}) {
  return (
    <section className="side-panel" aria-labelledby="decision-inbox-heading">
      <header>
        <h2 id="decision-inbox-heading">Decision Inbox</h2>
        <span>{rows.length}</span>
      </header>
      {rows.length > 0 ? (
        rows.map((row) => (
          <button
            className={`decision-row${
              row.id === selectedRowId ? " decision-row--active" : ""
            }`}
            key={row.id}
            onClick={() => onSelect(row.id)}
            type="button"
          >
            <strong>{row.title}</strong>
            <span>
              {repositoryLabel(row.repository_id, repositoryById)} - {row.reason_code}
            </span>
          </button>
        ))
      ) : (
        <p className="empty-state">No decisions</p>
      )}
    </section>
  );
}

function RecoverySignals({
  signals,
}: {
  signals: QueueWorkbenchRecoverySignal[];
}) {
  return (
    <section className="side-panel" aria-labelledby="recovery-signals-heading">
      <header>
        <h2 id="recovery-signals-heading">Recovery Signals</h2>
        <span>{signals.length}</span>
      </header>
      {signals.length > 0 ? (
        <ol className="signal-list">
          {signals.map((signal) => (
            <li className={`signal-row signal-row--${signal.severity}`} key={signal.id}>
              <strong>{signal.title}</strong>
              <span>
                {signal.count} · {signal.action}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-state">No recovery signals</p>
      )}
    </section>
  );
}

function EventFeed({
  events,
  title,
}: {
  events: QueueWorkbenchEvent[];
  title: string;
}) {
  return (
    <section className="side-panel" aria-labelledby={`${slug(title)}-heading`}>
      <header>
        <h2 id={`${slug(title)}-heading`}>{title}</h2>
        <span>{events.length}</span>
      </header>
      {events.length > 0 ? (
        <ol className="event-list">
          {events.map((event) => (
            <li key={event.id}>
              <strong>{event.summary}</strong>
              <span>
                {event.status ?? event.kind} · {formatDate(event.created_at)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-state">No events</p>
      )}
    </section>
  );
}

function EmptyDetail() {
  return (
    <section className="detail-panel">
      <h2>No work selected</h2>
    </section>
  );
}

function rowsFromSections(sections: QueueWorkbenchSection[]): QueueWorkbenchRow[] {
  return sections.flatMap((section) => section.rows);
}

function filterRows(
  rows: QueueWorkbenchRow[],
  query: string,
  selectedRepositoryIds: string[],
): QueueWorkbenchRow[] {
  const normalizedQuery = query.trim().toLowerCase();
  return rows.filter(
    (row) =>
      rowMatchesProject(row, selectedRepositoryIds) &&
      (!normalizedQuery || matchesRow(row, normalizedQuery)),
  );
}

function filterSections(
  sections: QueueWorkbenchSection[],
  activeSection: SectionId | typeof allSections,
  query: string,
  selectedRepositoryIds: string[],
): QueueWorkbenchSection[] {
  const normalizedQuery = query.trim().toLowerCase();
  return sections
    .filter((section) => activeSection === allSections || section.id === activeSection)
    .map((section) => {
      const rows = section.rows.filter(
        (row) =>
          rowMatchesProject(row, selectedRepositoryIds) &&
          (!normalizedQuery || matchesRow(row, normalizedQuery)),
      );
      return { ...section, count: rows.length, rows };
    });
}

function buildProjectOptions(
  rows: QueueWorkbenchRow[],
  repositories: Repository[],
): ProjectFilterOption[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const projectId = row.repository_id ?? unscopedProjectId;
    counts.set(projectId, (counts.get(projectId) ?? 0) + 1);
  }

  const knownRepositoryIds = new Set(repositories.map((repository) => repository.id));
  const options = repositories.map((repository) => ({
    id: repository.id,
    label: repository.name,
    count: counts.get(repository.id) ?? 0,
    syncStatus: repository.sync_status,
  }));

  const unscopedCount = counts.get(unscopedProjectId) ?? 0;
  if (unscopedCount > 0) {
    options.unshift({
      id: unscopedProjectId,
      label: "Unscoped",
      count: unscopedCount,
      syncStatus: "local",
    });
  }

  for (const [repositoryId, count] of counts) {
    if (repositoryId !== unscopedProjectId && !knownRepositoryIds.has(repositoryId)) {
      options.push({
        id: repositoryId,
        label: `Unknown project ${shortIdentifier(repositoryId)}`,
        count,
        syncStatus: "not registered",
      });
    }
  }

  return options;
}

function rowMatchesProject(
  row: QueueWorkbenchRow,
  selectedRepositoryIds: string[],
): boolean {
  if (selectedRepositoryIds.length === 0) {
    return true;
  }
  return selectedRepositoryIds.includes(row.repository_id ?? unscopedProjectId);
}

function repositoryLabel(
  repositoryId: string | null,
  repositoryById: Map<string, Repository>,
): string {
  if (!repositoryId) {
    return "Unscoped";
  }
  return (
    repositoryById.get(repositoryId)?.name ?? `Unknown project ${shortIdentifier(repositoryId)}`
  );
}

function matchesRow(row: QueueWorkbenchRow, normalizedQuery: string): boolean {
  return [
    row.title,
    row.status,
    row.reason_code,
    row.next_action,
    row.expected_touch ?? "",
    row.source_url ?? "",
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalizedQuery);
}

function formatDate(value: string | null): string {
  if (!value) {
    return "not recorded";
  }
  return new Date(value).toISOString().replace(".000Z", "Z");
}

function stringValue(value: unknown, fallback: string): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function slug(value: string): string {
  return value.toLowerCase().replace(/\s+/g, "-");
}

function shortIdentifier(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value;
}
