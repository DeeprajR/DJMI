import Link from "next/link";

export default function Home() {
  return (
    <main id="main-content" tabIndex={-1} className="page">
      <section className="landing-hero" aria-labelledby="welcome-heading">
        <div>
          <span className="role-badge role-doctor">Doctor workspace</span>
          <h1 id="welcome-heading" className="page-heading mt-6">Every request.<br />A clear next step.</h1>
          <p className="lead">From patient admission to blood sample association. Keep your blood request workflow in one focused workspace.</p>
          <div className="actions">
            <Link href="/sign-in" className="button button-primary">Sign in to your workspace</Link>
            <a href="#workflow" className="text-link">Explore the workflow</a>
          </div>
          <p className="page-description mt-5">Institution-provisioned accounts only. No public registration.</p>
        </div>
        <section id="workflow" className="panel" aria-labelledby="workflow-heading">
          <h2 id="workflow-heading" className="mb-6">From admission to sample</h2>
          <ol className="workflow-card">
            <li><span className="step-number">1</span><div><h3>Identify the admission</h3><p>Find the patient and confirm the IP No. and ward.</p></div></li>
            <li><span className="step-number">2</span><div><h3>Prepare and review</h3><p>Choose the product, blood group, units, and date needed.</p></div></li>
            <li><span className="step-number">3</span><div><h3>Submit and associate</h3><p>Generate a request ID and record associated blood samples.</p></div></li>
          </ol>
        </section>
      </section>
      <section className="feature-grid" aria-label="Workspace principles">
        <article className="panel"><h2>Patient context, together</h2><p>Patient and admission details follow each request, without re-entering identity fields.</p></article>
        <article className="panel"><h2>Review before submission</h2><p>Edit a draft, check its details, then submit. Submitted requests are read-only.</p></article>
        <article className="panel"><h2>Connected when it counts</h2><p>Install the app for quick access. Clinical data and changes always require a network connection.</p></article>
      </section>
    </main>
  );
}
