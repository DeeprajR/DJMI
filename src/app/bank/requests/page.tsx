import Link from "next/link";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db/client";
import { bankDecisions, bloodRequests } from "@/db/schema";
import { requireBank } from "@/lib/auth/bank-guard";
import { DONOR_RECRUITABLE_PRODUCTS, pendingRequestsWhere } from "@/lib/bank/demand";
import { bankMessages } from "@/lib/bank/schema";
import { getStockSummary } from "@/lib/bank/stock";
import { bloodProductLabelMap } from "@/lib/blood-request/draft";

type Props = { searchParams: Promise<{ notice?: string; error?: string }> };

export default async function BankRequestsPage({ searchParams }: Props) {
  await requireBank();
  const params = await searchParams;

  const pending = await db.query.bloodRequests.findMany({
    where: pendingRequestsWhere(),
    orderBy: [bloodRequests.dateNeeded, bloodRequests.submittedAt],
    limit: 100,
  });
  const decided = await db
    .select({
      id: bloodRequests.id,
      requestId: bloodRequests.requestId,
      group: bloodRequests.requestedBloodGroup,
      units: bloodRequests.units,
      dateNeeded: bloodRequests.dateNeeded,
      decision: bankDecisions.decision,
      unitsIssued: bankDecisions.unitsIssued,
      decidedAt: bankDecisions.decidedAt,
    })
    .from(bankDecisions)
    .innerJoin(bloodRequests, eq(bloodRequests.id, bankDecisions.bloodRequestId))
    .orderBy(desc(bankDecisions.decidedAt))
    .limit(30);

  const stock = await getStockSummary();
  const availableFor = (group: string | null) =>
    stock.find((s) => s.bloodGroup === group)?.available ?? 0;

  const notice = params.notice ? bankMessages[params.notice as keyof typeof bankMessages] : null;
  const error = params.error ? (bankMessages[params.error as keyof typeof bankMessages] ?? params.error) : null;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Requests from doctors</h1>
          <p className="page-description">
            Issue from stock, oldest expiry first. Anything you cannot issue goes to the donor bot.
          </p>
        </div>
        <Link className="button" href="/bank">Overview</Link>
      </header>

      {notice ? <div className="notice notice-success" role="status">{notice}</div> : null}
      {error ? <div className="notice notice-error" role="alert">{error}</div> : null}

      <section className="panel min-w-0" aria-labelledby="pending-heading">
        <h2 id="pending-heading">Awaiting decision ({pending.length})</h2>
        {pending.length === 0 ? (
          <p className="empty-state mt-5">Nothing waiting.</p>
        ) : (
          <div className="grid min-w-0 gap-6 mt-5">
            {pending.map((r) => {
              const available = availableFor(r.requestedBloodGroup);
              const units = r.units ?? 0;
              const canIssue = Math.min(units, available);
              const recruitable = r.product ? DONOR_RECRUITABLE_PRODUCTS.has(r.product) : false;
              return (
                <article key={r.id} className="panel min-w-0" aria-label={`Request ${r.requestId}`}>
                  <div className="page-header mb-5">
                    <div>
                      <h3>
                        <span className="blood-chip">{r.requestedBloodGroup}</span>{" "}
                        {units} unit{units === 1 ? "" : "s"} · {r.product ? bloodProductLabelMap[r.product] : "—"}
                      </h3>
                      <p className="page-description">
                        {r.requestId} · needed by {r.dateNeeded} · ward {r.wardNoSnapshot ?? "—"} · Dr {r.doctorNameSnapshot ?? "—"}
                      </p>
                      <p className="page-description">
                        In stock: <strong>{available}</strong> · can issue now: <strong>{canIssue}</strong>
                        {units > available ? ` · short by ${units - available}` : ""}
                      </p>
                    </div>
                  </div>
                  <form method="post" action="/api/bank/decisions" className="form-stack">
                    <input type="hidden" name="bloodRequestId" value={r.id} />
                    <label className="field">
                      Decision
                      <select name="decision" defaultValue={canIssue >= units ? "approved" : canIssue > 0 ? "partial" : "declined"} className="input">
                        <option value="approved">Approve — issue all {units}</option>
                        <option value="partial">Partial — issue what is in stock</option>
                        <option value="declined">Decline — issue nothing</option>
                      </select>
                    </label>
                    <label className="field">
                      Units to issue
                      <input name="unitsToIssue" type="number" min={0} max={units} defaultValue={canIssue} className="input" />
                    </label>
                    <label className="field">
                      Note to the doctor (optional)
                      <input name="note" type="text" maxLength={500} className="input" />
                    </label>
                    {recruitable ? (
                      <label className="field">
                        <span>
                          <input name="recruitDonors" type="checkbox" defaultChecked={units > available} /> Recruit donors for any shortfall
                        </span>
                      </label>
                    ) : (
                      <p className="page-description">Donors are not recruited for {r.product ? bloodProductLabelMap[r.product] : "this product"}.</p>
                    )}
                    <div className="actions">
                      <button type="submit" className="button button-primary">Record decision</button>
                      <Link className="button" href={`/requests/${r.id}/view`}>Open request</Link>
                    </div>
                  </form>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel min-w-0" aria-labelledby="decided-heading">
        <h2 id="decided-heading">Recent decisions</h2>
        {decided.length === 0 ? (
          <p className="empty-state mt-5">None yet.</p>
        ) : (
          <div className="table-scroll mt-5">
            <table className="data-table">
              <thead>
                <tr><th>Request</th><th>Group</th><th>Asked</th><th>Issued</th><th>Decision</th><th>When</th></tr>
              </thead>
              <tbody>
                {decided.map((d) => (
                  <tr key={d.id}>
                    <td><Link href={`/requests/${d.id}/view`}>{d.requestId}</Link></td>
                    <td><span className="blood-chip">{d.group}</span></td>
                    <td>{d.units}</td>
                    <td>{d.unitsIssued}</td>
                    <td><span className="status-pill">{d.decision}</span></td>
                    <td>{new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(d.decidedAt)}</td>
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
