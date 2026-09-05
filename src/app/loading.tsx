export default function Loading() {
  return (
    <main id="main-content" tabIndex={-1} className="page page-narrow" aria-busy="true">
      <section className="panel" role="status" aria-live="polite">
        <h1 className="page-heading">Loading your workspace</h1>
        <p className="page-description">Retrieving the latest information. Please wait before making changes.</p>
      </section>
    </main>
  );
}