import Link from "next/link";
import { and, desc, eq, inArray, sql } from "drizzle-orm";
import { db } from "@/db/client";
import { bloodRequests, donorDemand } from "@/db/schema";
import { requireBank } from "@/lib/auth/bank-guard";
import { demandStatusLabel, pendingRequestsWhere } from "@/lib/bank/demand";
import { getBankSettings, getStockSummary } from "@/lib/bank/stock";

type Props = { searchParams: Promise<{ notice?: string; error?: string }> };

export default async function BankOverviewPage({ searchParams }: Props) {
  await requireBank();
  const params = await searchParams;

  const settings = await getBankSettings();
  const stock = await getStockSummary(settings);

  const [pendingRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(bloodRequests)
    .where(pendingRequestsWhere());

  const openDemand = await db.query.donorDemand.findMany({
    where: inArray(donorDemand.status, ["open", "fulfilled"]),
    orderBy: [desc(donorDemand.createdAt)],
    limit: 10,
  });

  const [issuedTodayRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(donorDemand)
    .where(and(eq(donorDemand.status, "completed"), sql`${donorDemand.closedAt} >= current_date`));

  const belowFloor = stock.filter((s) => s.shortfall > 0);
  const totalAvailable = stock.reduce((n, s) => n + s.available, 0);

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Blood bank</h1>
          <p className="page-description">
            {settings.hospitalName} · stock against a {settings.minUnitsPerGroup}-unit floor per group
          </p>
        </div>
        <div className="actions">
          <Link className="button" href="/bank/inventory">Inventory</Link>
          <Link className="button button-primary" href="/bank/requests">
            Requests{pendingRow?.count ? ` (${pendingRow.count})` : ""}
          </Link>
        </div>
      </header>

      {params.notice ? <div className="notice notice-success" role="status">{params.notice}</div> : null}
      {params.error ? <div className="notice notice-error" role="alert">{params.error}</div> : null}

      <section className="metric-grid" aria-label="Summary">
        <div className="metric-card">
          <span>Units available</span>
          <span className="metric-value">{totalAvailable}</span>
        </div>
        <div className="metric-card">
          <span>Groups below floor</span>
          <span className="metric-value">{belowFloor.length}</span>
        </div>
        <div className="metric-card">
          <span>Requests awaiting decision</span>
          <span className="metric-value">{pendingRow?.count ?? 0}</span>
        </div>
        <div className="metric-card">
          <span>Donor drives completed today</span>
          <span className="metric-value">{issuedTodayRow?.count ?? 0}</span>
        </div>
      </section>

      <section className="panel min-w-0" aria-labelledby="stock-heading">
        <div className="page-header mb-5">
          <h2 id="stock-heading">Stock by group</h2>
          {belowFloor.length > 0 ? (
            <form method="post" action="/api/bank/demand/floor">
              <button type="submit" className="button button-primary">
                Recruit donors for {belowFloor.length} group{belowFloor.length === 1 ? "" : "s"} below floor
              </button>
            </form>
          ) : null}
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Group</th>
                <th>Available</th>
                <th>Reserved</th>
                <th>Floor</th>
                <th>Shortfall</th>
                <th>Expiring in 7 days</th>
              </tr>
            </thead>
            <tbody>
              {stock.map((line) => (
                <tr key={line.bloodGroup}>
                  <td><span className="blood-chip">{line.bloodGroup}</span></td>
                  <td>{line.available}</td>
                  <td>{line.reserved}</td>
                  <td>{line.floor}</td>
                  <td>
                    {line.shortfall > 0 ? (
                      <span className="status-pill status-draft">−{line.shortfall}</span>
                    ) : (
                      <span className="status-pill status-submitted">OK</span>
                    )}
                  </td>
                  <td>{line.expiringSoon}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel min-w-0" aria-labelledby="demand-heading">
        <div className="page-header mb-5">
          <h2 id="demand-heading">Donor recruitment in progress</h2>
          <Link className="button" href="/bank/demand">All demand</Link>
        </div>
        {openDemand.length === 0 ? (
          <p className="empty-state">No donor recruitment running.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Units</th>
                  <th>Confirmed</th>
                  <th>Notified</th>
                  <th>Needed by</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {openDemand.map((d) => (
                  <tr key={d.id}>
                    <td><span className="blood-chip">{d.bloodGroup}</span></td>
                    <td>{d.units}</td>
                    <td>{d.confirmedUnits}/{d.units}</td>
                    <td>{d.notifiedDonors}</td>
                    <td>{d.dateNeeded}</td>
                    <td>
                      <span className="status-pill">{demandStatusLabel[d.status] ?? d.status}</span>
                      {!d.botPublicId ? <span className="page-description"> · waiting for bot</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
