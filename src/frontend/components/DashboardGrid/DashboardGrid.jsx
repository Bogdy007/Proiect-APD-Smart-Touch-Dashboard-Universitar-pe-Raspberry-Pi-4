import './DashboardGrid.css';

export default function DashboardGrid({ statusBar, widgets }) {
  return (
    <div className="dashboard">
      <header className="dashboard__status">{statusBar}</header>

      <main className="dashboard__grid">
        {widgets.map((widget) => (
          <section
            key={widget.id}
            className="dashboard__slot"
            aria-label={widget.title}
          >
            {widget.element}
          </section>
        ))}
      </main>
    </div>
  );
}