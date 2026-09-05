import { and, desc, eq, gte, sql } from "drizzle-orm";
import { requireDoctor } from "@/lib/auth/guard";
import Link from "next/link";
import { admissions, bloodRequests } from "@/db/schema";
import { db } from "@/db/client";
import { bloodProductLabelMap } from "@/lib/blood-request/draft";

function statusBadgeClass(status: string): string {
  if (status === "submitted") {
    return "status-pill status-submitted";
  }
  if (status === "draft") {
    return "status-pill status-draft";
  }
  return "status-pill";
}

function formatDateTime(date: Date): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default async function DashboardPage() {
  const doctor = await requireDoctor();

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  const [activeAdmissionsRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(admissions)
    .where(eq(admissions.admissionStatus, "active"));

  const [draftRequestsRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(bloodRequests)
    .where(and(eq(bloodRequests.doctorId, doctor.id), eq(bloodRequests.status, "draft")));

  const [submittedTodayRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(bloodRequests)
    .where(
      and(
        eq(bloodRequests.doctorId, doctor.id),
        eq(bloodRequests.status, "submitted"),
        gte(bloodRequests.submittedAt, todayStart)
      )
    );

  const samplesPendingResult = await db.execute<{ count: number }>(sql`
    SELECT count(*)::int AS count
    FROM blood_requests br
    WHERE br.doctor_id = ${doctor.id}
      AND br.status = 'submitted'
      AND NOT EXISTS (
        SELECT 1
        FROM blood_samples bs
        WHERE bs.blood_request_id = br.id
      )
  `);

  const recentRequests = await db.query.bloodRequests.findMany({
    where: eq(bloodRequests.doctorId, doctor.id),
    with: {
      admission: {
        with: {
          patient: true,
        },
      },
    },
    orderBy: [desc(bloodRequests.updatedAt)],
    limit: 20,
  });

  const activeAdmissions = activeAdmissionsRow?.count ?? 0;
  const draftRequests = draftRequestsRow?.count ?? 0;
  const submittedToday = submittedTodayRow?.count ?? 0;
  const samplesPending = samplesPendingResult.rows[0]?.count ?? 0;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div className="min-w-0">
          <span className="role-badge role-doctor">{doctor.role === "admin" ? "Admin" : "Doctor"}</span>
          <h1 className="page-heading">Overview</h1>
          <p className="page-description break-words">
            Signed in as {doctor.doctorName} ({doctor.doctorProvisionalReg})
          </p>
        </div>
        <div className="actions">
          <Link href="/requests/new" className="button button-primary">
            New blood request
          </Link>
          <form method="post" action="/api/auth/sign-out">
            <button type="submit" className="button">Sign out</button>
          </form>
        </div>
      </header>

      <section className="metric-grid" aria-label="Request and admission summary">
        <div className="metric-card">
          <p className="page-description">Active admissions</p>
          <p className="metric-value">{activeAdmissions}</p>
        </div>
        <div className="metric-card">
          <p className="page-description">My draft requests</p>
          <p className="metric-value">{draftRequests}</p>
        </div>
        <div className="metric-card">
          <p className="page-description">Submitted today</p>
          <p className="metric-value">{submittedToday}</p>
        </div>
        <div className="metric-card">
          <p className="page-description">Samples pending</p>
          <p className="metric-value">{samplesPending}</p>
        </div>
      </section>

      <section className="panel min-w-0">
        <div className="page-header mb-5">
          <h2>Recent requests</h2>
          <Link href="/admissions" className="button">
            Find admission
          </Link>
        </div>

        <div className="table-scroll" role="region" tabIndex={0} aria-label="Recent requests">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Request ID</th>
                <th scope="col">IP No.</th>
                <th scope="col">Patient</th>
                <th scope="col">Product</th>
                <th scope="col">Units</th>
                <th scope="col">Date needed</th>
                <th scope="col">Status</th>
                <th scope="col">Updated</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {recentRequests.length === 0 ? (
                <tr>
                  <td colSpan={9} className="empty-state">
                    No requests found.
                  </td>
                </tr>
              ) : (
                recentRequests.map((request) => (
                  <tr key={request.id}>
                    <td>{request.requestId || "Draft"}</td>
                    <td>{request.ipNo}</td>
                    <td>{request.admission.patient.patientName}</td>
                    <td>
                      {request.product ? bloodProductLabelMap[request.product] : "-"}
                    </td>
                    <td>{request.units ?? "-"}</td>
                    <td>{request.dateNeeded ?? "-"}</td>
                    <td>
                      <span className={statusBadgeClass(request.status)}>
                        {request.status.charAt(0).toUpperCase() + request.status.slice(1)}
                      </span>
                    </td>
                    <td>{formatDateTime(request.updatedAt)}</td>
                    <td>
                      {request.status === "draft" ? (
                        <Link
                          href={`/requests/${request.id}`}
                          className="button"
                        >
                          Open draft
                        </Link>
                      ) : (
                        <Link
                          href={`/requests/${request.id}/view`}
                          className="button"
                        >
                          View request
                        </Link>
                      )}
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
