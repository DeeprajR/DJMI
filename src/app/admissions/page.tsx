import Link from "next/link";
import { and, eq, ilike } from "drizzle-orm";
import type { SQL } from "drizzle-orm";
import { db } from "@/db/client";
import { admissions } from "@/db/schema";
import { requireDoctor } from "@/lib/auth/guard";

type AdmissionsPageProps = {
  searchParams: Promise<{
    ipNo?: string;
    status?: string;
    patientId?: string;
    created?: string;
    error?: string;
  }>;
};

function admissionError(code?: string): string | null {
  if (code === "invalid_admission") {
    return "Invalid admission input.";
  }
  if (code === "patient_not_found") {
    return "Patient was not found.";
  }
  if (code === "duplicate_ip") {
    return "IP No. already exists.";
  }
  return null;
}

export default async function AdmissionsPage({ searchParams }: AdmissionsPageProps) {
  await requireDoctor();
  const params = await searchParams;

  const ipNoQuery = (params.ipNo || "").trim();
  const statusQuery = (params.status || "").trim();

  const whereClauses: SQL[] = [];
  if (ipNoQuery) {
    whereClauses.push(ilike(admissions.ipNo, `%${ipNoQuery}%`));
  }
  if (statusQuery === "active" || statusQuery === "discharged") {
    whereClauses.push(eq(admissions.admissionStatus, statusQuery));
  }

  const records = await db.query.admissions.findMany({
    where: whereClauses.length > 0 ? and(...whereClauses) : undefined,
    with: {
      patient: true,
    },
    orderBy: (table, { desc }) => [desc(table.admittedAt)],
    limit: 100,
  });

  const createdMessage = params.created === "1" ? `Admission created (${params.ipNo || "IP unavailable"}).` : null;
  const errorMessage = admissionError(params.error);
  const patientPrefill = (params.patientId || "").trim();

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Admissions</h1>
          <p className="page-description">Manage admission context before creating blood requests.</p>
        </div>
      </header>

      {createdMessage ? (
        <div className="notice notice-success" role="status">
          {createdMessage}
        </div>
      ) : null}

      {errorMessage ? (
        <div className="notice notice-error" role="alert">{errorMessage}</div>
      ) : null}

      <section className="grid min-w-0 items-start gap-6 md:grid-cols-2">
        <div className="panel min-w-0">
          <h2>Create admission</h2>
          <form method="post" action="/api/admissions" className="form-stack mt-5">
            <label className="field">
              IP No. of Patient
              <input
                name="ipNo"
                type="text"
                required
                className="input"
              />
            </label>

            <label className="field">
              Patient ID
              <input
                name="patientId"
                type="text"
                required
                defaultValue={patientPrefill}
                className="input"
              />
            </label>

            <label className="field">
              Ward No.
              <input
                name="wardNo"
                type="text"
                required
                className="input"
              />
            </label>

            <button
              type="submit"
              className="button button-primary"
            >
              Create admission
            </button>
          </form>
        </div>

        <div className="panel min-w-0">
          <h2>Search admissions</h2>
          <form method="get" className="form-stack mt-5">
            <label className="field">
              IP No.
              <input
                name="ipNo"
                defaultValue={ipNoQuery}
                placeholder="IP No."
                className="input"
              />
            </label>
            <label className="field">
              Admission status
              <select
                name="status"
                defaultValue={statusQuery}
                className="input"
              >
                <option value="">All status</option>
                <option value="active">active</option>
                <option value="discharged">discharged</option>
              </select>
            </label>
            <button type="submit" className="button">
              Search
            </button>
          </form>
        </div>
      </section>

      <section className="panel min-w-0">
        <h2 className="mb-5">Admission records</h2>
        <div className="table-scroll" role="region" tabIndex={0} aria-label="Admission records">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">IP No. of Patient</th>
                <th scope="col">Ward No.</th>
                <th scope="col">Admission status</th>
                <th scope="col">Patient name</th>
                <th scope="col">Age of Patient</th>
                <th scope="col">Blood Group of Patient</th>
                <th scope="col">Admitted at</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-state">
                    No admissions found.
                  </td>
                </tr>
              ) : (
                records.map((row) => (
                  <tr key={row.ipNo}>
                    <td>{row.ipNo}</td>
                    <td>{row.wardNo}</td>
                    <td>
                      <span className="status-pill">
                        {row.admissionStatus.charAt(0).toUpperCase() + row.admissionStatus.slice(1)}
                      </span>
                    </td>
                    <td>{row.patient.patientName}</td>
                    <td>
                      {row.patient.patientAge} {row.patient.patientAgeUnit}
                    </td>
                    <td><span className="blood-chip">{row.patient.patientBloodGroup}</span></td>
                    <td>{row.admittedAt.toISOString()}</td>
                    <td>
                      <Link
                        href={`/requests/new?ipNo=${encodeURIComponent(row.ipNo)}`}
                        className="button"
                      >
                        Create blood request
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
