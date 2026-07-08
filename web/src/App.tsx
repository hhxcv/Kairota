import "./styles.css";

type QueueSection = {
  id: string;
  title: string;
  count: number;
  tone: "green" | "blue" | "amber" | "red" | "gray";
  rows: string[];
};

const sections: QueueSection[] = [
  { id: "ready", title: "Ready", count: 0, tone: "green", rows: [] },
  { id: "running", title: "Running", count: 0, tone: "blue", rows: [] },
  { id: "blocked", title: "Blocked", count: 0, tone: "amber", rows: [] },
  { id: "waiting", title: "Waiting", count: 0, tone: "gray", rows: [] },
  { id: "failed", title: "Failed", count: 0, tone: "red", rows: [] },
  { id: "done", title: "Done", count: 0, tone: "green", rows: [] },
];

function QueueColumn({ section }: { section: QueueSection }) {
  return (
    <section className="queue-column" aria-labelledby={`${section.id}-heading`}>
      <header className="queue-column__header">
        <h2 id={`${section.id}-heading`}>{section.title}</h2>
        <span className={`status-pill status-pill--${section.tone}`}>
          {section.count}
        </span>
      </header>
      <div className="queue-column__body">
        {section.rows.length > 0 ? (
          section.rows.map((row) => (
            <article className="work-row" key={row}>
              {row}
            </article>
          ))
        ) : (
          <p className="empty-state">No work</p>
        )}
      </div>
    </section>
  );
}

export function App() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI Dev Queue</p>
          <h1>Kairota</h1>
        </div>
        <div className="sync-state">
          <span className="sync-state__dot" />
          Local runtime foundation
        </div>
      </header>

      <section className="queue-grid" aria-label="Queue sections">
        {sections.map((section) => (
          <QueueColumn key={section.id} section={section} />
        ))}
      </section>
    </main>
  );
}
