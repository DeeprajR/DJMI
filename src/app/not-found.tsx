import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main-content" tabIndex={-1} className="page page-narrow">
      <header><p className="eyebrow mb-4">Page not found</p><h1 className="page-heading">This page isn’t available</h1></header>
      <p className="page-description">The address may be incorrect, or the record may not be available to your account.</p>
      <div className="actions"><Link className="button" href="/dashboard">Back to overview</Link></div>
    </main>
  );
}