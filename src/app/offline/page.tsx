import Link from "next/link";

export default function OfflinePage() {
  return (
    <main id="main-content" tabIndex={-1} className="page page-narrow">
      <header className="page-header"><h1 className="page-heading">You’re offline</h1></header>
      <section className="notice notice-offline" role="status">
        <h2>A connection is needed to continue</h2>
        <p className="mt-3">
          The app shell is available, but patient details, requests, and all changes require a network connection. No changes are queued for later.
        </p>
      </section>
      <div className="actions"><Link href="/dashboard" className="button" prefetch={false}>Try your workspace again</Link></div>
    </main>
  );
}
