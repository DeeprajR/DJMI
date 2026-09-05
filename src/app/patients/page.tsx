import Link from "next/link";
import { and, eq, ilike } from "drizzle-orm";
import type { SQL } from "drizzle-orm";
import { db } from "@/db/client";
import { patients } from "@/db/schema";
import { requireDoctor } from "@/lib/auth/guard";

const bloodGroups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] as const;

type PatientsPageProps = {
  searchParams: Promise<{
    q?: string;
    bloodGroup?: string;
    created?: string;
    patientId?: string;
    error?: string;
  }>;
};

function patientError(code?: string): string | null {
  if (code === "invalid_patient") {
    return "Invalid patient input.";
  }
  return null;
}

export default async function PatientsPage({ searchParams }: PatientsPageProps) {
  await requireDoctor();
  const params = await searchParams;

  const nameQuery = (params.q || "").trim();
  const bgQuery = (params.bloodGroup || "").trim();

  const whereClauses: SQL[] = [];
  if (nameQuery) {
    whereClauses.push(ilike(patients.patientName, `%${nameQuery}%`));
  }
  if (bloodGroups.includes(bgQuery as (typeof bloodGroups)[number])) {
    whereClauses.push(eq(patients.patientBloodGroup, bgQuery as (typeof bloodGroups)[number]));
  }

  const records = await db.query.patients.findMany({
    where: whereClauses.length > 0 ? and(...whereClauses) : undefined,
    orderBy: (table, { desc }) => [desc(table.createdAt)],
    limit: 100,
  });

  const createdMessage = params.created === "1" ? `Patient created (${params.patientId || "id unavailable"}).` : null;
  const errorMessage = patientError(params.error);

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Patients</h1>
          <p className="page-description">Create and search patients before admission selection.</p>
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
          <h2>Create patient</h2>
          <form method="post" action="/api/patients" className="form-stack mt-5">
            <label className="field">
              Name of Patient
              <input
                name="patientName"
                type="text"
                required
                className="input"
              />
            </label>

            <label className="field">
              Age of Patient
              <input
                name="patientAge"
                type="number"
                min={0}
                required
                className="input"
              />
            </label>

            <label className="field">
              Age Unit
              <select
                name="patientAgeUnit"
                defaultValue="years"
                className="input"
              >
                <option value="days">days</option>
                <option value="months">months</option>
                <option value="years">years</option>
              </select>
            </label>

            <label className="field">
              Blood Group of Patient
              <select
                name="patientBloodGroup"
                defaultValue=""
                required
                className="input"
              >
                <option value="" disabled>
                  Select blood group
                </option>
                {bloodGroups.map((group) => (
                  <option key={group} value={group}>
                    {group}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="submit"
              className="button button-primary"
            >
              Create patient
            </button>
          </form>
        </div>

        <div className="panel min-w-0">
          <h2>Search patients</h2>
          <form method="get" className="form-stack mt-5">
            <label className="field">
              Patient name
              <input
                name="q"
                defaultValue={nameQuery}
                placeholder="Patient name"
                className="input"
              />
            </label>
            <label className="field">
              Blood group
              <select
                name="bloodGroup"
                defaultValue={bgQuery}
                className="input"
              >
                <option value="">All groups</option>
                {bloodGroups.map((group) => (
                  <option key={group} value={group}>
                    {group}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="button">
              Search
            </button>
          </form>
        </div>
      </section>

      <section className="panel min-w-0">
        <h2 className="mb-5">Patient records</h2>
        <div className="table-scroll" role="region" tabIndex={0} aria-label="Patient records">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Patient ID</th>
                <th scope="col">Name of Patient</th>
                <th scope="col">Age of Patient</th>
                <th scope="col">Blood Group of Patient</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty-state">
                    No patients found.
                  </td>
                </tr>
              ) : (
                records.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{row.patientName}</td>
                    <td>
                      {row.patientAge} {row.patientAgeUnit}
                    </td>
                    <td><span className="blood-chip">{row.patientBloodGroup}</span></td>
                    <td>
                      <Link
                        href={`/admissions?patientId=${row.id}`}
                        className="button"
                      >
                        Create admission
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
