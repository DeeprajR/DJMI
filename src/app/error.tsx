"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main-content" tabIndex={-1} className="page page-narrow">
      <h1 className="page-heading">We couldn’t load this page</h1>
      <section className="notice notice-error" role="alert">
        <h2>Please check your connection</h2>
        <p className="mt-3">If you were saving a change, check the latest record before submitting again. Contact your administrator if the problem continues.</p>
      </section>
      <div className="actions"><button className="button" onClick={reset}>Try again</button></div>
    </main>
  );
}