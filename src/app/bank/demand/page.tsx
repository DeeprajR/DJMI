import Link from "next/link";
import { desc, inArray } from "drizzle-orm";
import { db } from "@/db/client";
import { donorDemand, donorDemandConfirmations } from "@/db/schema";
import { requireBank } from "@/lib/auth/bank-guard";
import { demandStatusLabel } from "@/lib/bank/demand";
import { bankMessages } from "@/lib/bank/schema";
import { todayIso } from "@/lib/bank/route-helpers";

type Props = { searchParams: Promise<{ show?: string; notice?: string; error?: string }> };

const BOT_USERNAME = process.env.NEXT_PUBLIC_BOT_USERNAME ?? "";

function confirmationClass(status: string): string {
  if (status === "completed") return "status-pill status-submitted";
  if (status === "confirmed") return "status-pill";
  return "status-pill status-draft";
}

export default async function DemandPage({ searchParams }: Props) {
  await requireBank();
  const params = await searchParams;
  const showAll = params.show === "all";

  const demands = await db.query.donorDemand.findMany({
    where: showAll ? undefined : inArray(donorDemand.status, ["open", "fulfilled"]),
    orderBy: [desc(donorDemand.createdAt)],
    limit: 50,
    with: {
      confirmations: { orderBy: [donorDemandConfirmations.confirmedAt] },
      bloodRequest: { columns: { requestId: true, id: true } },
    },
  });

  const notice = params.notice ? bankMessages[params.notice as keyof typeof bankMessages] : null;
  const error = params.error ? (bankMessages[params.error as keyof typeof bankMessages] ?? params.error) : null;
  const today = todayIso();

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Donor demand</h1>
          <p className="page-description">
            What the Telegram bot is recruiting for, who has confirmed, and the counter&apos;s marks.
          </p>
        </div>
        <div className="actions">
          <Link className="button" href={showAll ? "/bank/demand" : "/bank/demand?show=all"}>
            {showAll ? "Active only" : "Show all"}
          </Link>
          <Link className="button" href="/bank">Overview</Link>
        </div>
      </header>

      {notice ? <div className="notice notice-success" role="status">{notice}</div> : null}
      {error ? <div className="notice notice-error" role="alert">{error}</div> : null}

      {demands.length === 0 ? (
        <section className="panel min-w-0"><p className="empty-state">No donor demand{showAll ? "" : " in progress"}.</p></section>
      ) : (
        demands.map((d) => {
          const active = d.status === "open" || d.status === "fulfilled";
          const link = d.botPublicId && BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=req_${d.botPublicId}` : null;
          return (
            <section key={d.id} className="panel min-w-0" aria-label={`Demand ${d.bloodGroup}`}>
              <div className="page-header mb-5">
                <div>
                  <h2>
                    <span className="blood-chip">{d.bloodGroup}</span> {d.units} unit{d.units === 1 ? "" : "s"}
                    {" "}· <span className="status-pill">{demandStatusLabel[d.status] ?? d.status}</span>
                  </h2>
                  <p className="page-description">
                    {d.trigger === "stock_floor" ? "Restocking to floor" : d.bloodRequest?.requestId ? <>For request <Link href={`/requests/${d.bloodRequest.id}/view`}>{d.bloodRequest.requestId}</Link></> : "Request shortfall"}
                    {" "}· needed by {d.dateNeeded} · raised {new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(d.createdAt)}
                  </p>
                  <p className="page-description">
                    {d.botPublicId ? (
                      <>
                        Bot: <strong>{d.confirmedUnits}/{d.units} confirmed</strong> · {d.waitlistedUnits} waitlisted · {d.notifiedDonors} notified · {d.completedUnits} donated
                        {link ? <> · <a href={link}>share link</a></> : null}
                      </>
                    ) : (
                      <>Waiting for the bot to pick this up (it polls every minute).</>
                    )}
                  </p>
                </div>
                {active ? (
                  <form method="post" action="/api/bank/demand/cancel">
                    <input type="hidden" name="demandId" value={d.id} />
                    <button type="submit" className="button">Withdraw</button>
                  </form>
                ) : null}
              </div>

              {d.confirmations.length === 0 ? (
                <p className="empty-state">No donors confirmed yet.</p>
              ) : (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr><th>Donor</th><th>Phone</th><th>Group</th><th>Confirmed</th><th>Status</th><th>At the counter</th></tr>
                    </thead>
                    <tbody>
                      {d.confirmations.map((c) => (
                        <tr key={c.id}>
                          <td>{c.donorName ?? c.telegramUserId}</td>
                          <td>{c.donorPhone ?? "—"}</td>
                          <td>{c.bloodGroup ? <span className="blood-chip">{c.bloodGroup}</span> : "—"}</td>
                          <td>{new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(c.confirmedAt)}</td>
                          <td>
                            <span className={confirmationClass(c.status)}>{c.status}</span>
                            {c.donatedAt ? <span className="page-description"> {c.donatedAt}{c.bagRfidTag ? ` · ${c.bagRfidTag}` : ""}</span> : null}
                          </td>
                          <td>
                            {c.status === "confirmed" ? (
                              <form method="post" action="/api/bank/confirmations" className="actions">
                                <input type="hidden" name="confirmationId" value={c.id} />
                                <input name="donatedAt" type="date" defaultValue={today} className="input" aria-label="Donated on" />
                                <input name="bagRfidTag" type="text" placeholder="bag RFID" className="input" aria-label="Bag RFID tag" />
                                <button type="submit" name="status" value="completed" className="button button-primary">Donated</button>
                                <button type="submit" name="status" value="no_show" className="button">No-show</button>
                                <button type="submit" name="status" value="cancelled" className="button">Cancelled</button>
                              </form>
                            ) : c.botAcknowledgedAt ? (
                              <span className="page-description">bot notified</span>
                            ) : (
                              <span className="page-description">bot will notify</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          );
        })
      )}
    </main>
  );
}
