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

import { fetchQueueWorkbench } from "./api";
import "./styles.css";
import {
  allRows,
  emptyWorkbench,
  sectionTones,
  type QueueWorkbench,
  type QueueWorkbenchEvent,
  type QueueWorkbenchRecoverySignal,
  type QueueWorkbenchRow,
  type QueueWorkbenchSection,
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

export function App() {
  const [workbench, setWorkbench] = useState<QueueWorkbench>(emptyWorkbench);
  const [source, setSource] = useState<DataSource>("empty");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<SectionId | typeof allSections>(
    allSections,
  );
  const [query, setQuery] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string>("");

  const loadWorkbench = useCallback(async (signal?: AbortSignal) => {
    setLoadState("loading");
    try {
      const data = await fetchQueueWorkbench(signal);
      setWorkbench(data);
      setSource("api");
      setLoadError(null);
      setSelectedRowId((current) => current || allRows(data)[0]?.id || "");
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setWorkbench(emptyWorkbench);
      setSource("empty");
      setLoadError(error instanceof Error ? error.message : "Request failed");
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
  const filteredSections = useMemo(
    () => filterSections(workbench.sections, activeSection, query),
    [activeSection, query, workbench.sections],
  );
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;

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
            count={workbench.summary.total}
            label="All"
            onClick={() => setActiveSection(allSections)}
          />
          {workbench.sections.map((section) => (
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
              {source === "api" ? "Local API" : "No API data"} - {rows.length} visible
              work items
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

        <SummaryStrip
          decisionCount={workbench.decision_inbox.length}
          failureCount={workbench.failures.length}
          summary={workbench.summary}
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
                section={section}
                selectedRowId={selectedRow?.id ?? ""}
              />
            ))}
          </section>

          <aside className="detail-rail" aria-label="Work item details">
            {selectedRow ? <DetailPanel row={selectedRow} /> : <EmptyDetail />}
            <DecisionInbox
              onSelect={setSelectedRowId}
              rows={workbench.decision_inbox}
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

function SummaryStrip({
  decisionCount,
  failureCount,
  summary,
}: {
  decisionCount: number;
  failureCount: number;
  summary: QueueWorkbench["summary"];
}) {
  const metrics = [
    ["Total", summary.total],
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
  section,
  selectedRowId,
}: {
  onSelect: (rowId: string) => void;
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
  row,
  selected,
}: {
  onSelect: (rowId: string) => void;
  row: QueueWorkbenchRow;
  selected: boolean;
}) {
  return (
    <button
      className={`work-row${selected ? " work-row--selected" : ""}`}
      onClick={() => onSelect(row.id)}
      type="button"
    >
      <span className="work-row__title">{row.title}</span>
      <span className="work-row__meta">
        P{row.priority} - {row.risk} - {row.work_type}
      </span>
      <span className="work-row__reason">{row.reason_code}</span>
      <span className="work-row__action">{row.next_action}</span>
    </button>
  );
}

function DetailPanel({ row }: { row: QueueWorkbenchRow }) {
  const repository = row.repository;
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
      </div>
      <DetailText label="Reason" value={row.reason_code} />
      <DetailText label="Next Action" value={row.next_action} />
      <DetailText label="Expected Touch" value={row.expected_touch ?? "not set"} />
      <DetailText label="Acceptance" value={row.acceptance ?? "not set"} />
      <DetailText label="Validation" value={row.validation ?? "not set"} />
      <TagGroup label="Conflicts" values={row.conflict_keys} />
      <TagGroup label="Dependencies" values={row.dependency_ids} />
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
  rows,
  selectedRowId,
}: {
  onSelect: (rowId: string) => void;
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
            <span>{row.reason_code}</span>
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

function filterSections(
  sections: QueueWorkbenchSection[],
  activeSection: SectionId | typeof allSections,
  query: string,
): QueueWorkbenchSection[] {
  const normalizedQuery = query.trim().toLowerCase();
  return sections
    .filter((section) => activeSection === allSections || section.id === activeSection)
    .map((section) => {
      const rows = normalizedQuery
        ? section.rows.filter((row) =>
            [
              row.title,
              row.status,
              row.reason_code,
              row.next_action,
              row.expected_touch ?? "",
            ]
              .join(" ")
              .toLowerCase()
              .includes(normalizedQuery),
          )
        : section.rows;
      return { ...section, count: rows.length, rows };
    });
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
