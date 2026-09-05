import { and, desc, eq, inArray } from "drizzle-orm";
import type { SQL } from "drizzle-orm";
import { db } from "@/db/client";
import { bloodBags } from "@/db/schema";
import { requireBank } from "@/lib/auth/bank-guard";
import { bankMessages } from "@/lib/bank/schema";
import { getStockSummary } from "@/lib/bank/stock";
import { bloodGroupValues, bloodProductLabelMap, bloodProductValues } from "@/lib/blood-request/draft";

type Props = {
  searchParams: Promise<{ group?: string; status?: string; notice?: string; error?: string }>;
};

const statuses = ["available", "reserved", "issued", "discarded", "expired"] as const;

function statusClass(status: string): string {
  if (status === "available") return "status-pill status-submitted";
  if (status === "issued") return "status-pill";
  return "status-pill status-draft";
}

export default async function InventoryPage({ searchParams }: Props) {
  await requireBank();
  const params = await searchParams;

  const groupFilter = bloodGroupValues.includes(params.group as (typeof bloodGroupValues)[number])
    ? (params.group as (typeof bloodGroupValues)[number])
    : null;
  const statusFilter = statuses.includes(params.status as (typeof statuses)[number])
    ? (params.status as (typeof statuses)[number])
    : "available";

  const where: SQL[] = [];
  if (groupFilter) where.push(eq(bloodBags.bloodGroup, groupFilter));
  if (statusFilter === "available") where.push(inArray(bloodBags.status, ["available", "reserved"]));
  else where.push(eq(bloodBags.status, statusFilter));

  const bags = await db.query.bloodBags.findMany({
    where: where.length ? and(...where) : undefined,
    orderBy: [desc(bloodBags.createdAt)],
    limit: 200,
  });
  const stock = await getStockSummary();

  const today = new Date().toISOString().slice(0, 10);
  const defaultExpiry = new Date();
  defaultExpiry.setDate(defaultExpiry.getDate() + 35); // whole blood, CPDA-1
  const notice = params.notice ? bankMessages[params.notice as keyof typeof bankMessages] : null;
  const error = params.error ? bankMessages[params.error as keyof typeof bankMessages] ?? params.error : null;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Inventory</h1>
          <p className="page-description">
            One row per bag. The RFID tag is the bag&apos;s identity — type it, or let the reader post it.
          </p>
        </div>
      </header>

      {notice ? <div className="notice notice-success" role="status">{notice}</div> : null}
      {error ? <div className="notice notice-error" role="alert">{error}</div> : null}

      <section className="grid min-w-0 items-start gap-6 md:grid-cols-2">
        <div className="panel min-w-0">
          <h2>Add a bag</h2>
          <form method="post" action="/api/bank/bags" className="form-stack mt-5">
            <label className="field">
              RFID tag
              <input name="rfidTag" type="text" required autoComplete="off" className="input" placeholder="scan or type" />
            </label>
            <label className="field">
              Blood group
              <select name="bloodGroup" defaultValue="" required className="input">
                <option value="" disabled>Select</option>
                {bloodGroupValues.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <label className="field">
              Product
              <select name="product" defaultValue="whole_blood" className="input">
                {bloodProductValues.map((p) => <option key={p} value={p}>{bloodProductLabelMap[p]}</option>)}
              </select>
            </label>
            <label className="field">
              Collected on
              <input name="collectedAt" type="date" required defaultValue={today} className="input" />
            </label>
            <label className="field">
              Expires on
              <input name="expiresAt" type="date" required defaultValue={defaultExpiry.toISOString().slice(0, 10)} className="input" />
            </label>
            <div className="actions">
              <button type="submit" className="button button-primary">Add to stock</button>
            </div>
          </form>
        </div>

        <div className="panel min-w-0">
          <h2>Stock at a glance</h2>
          <div className="table-scroll mt-5">
            <table className="data-table">
              <thead><tr><th>Group</th><th>Available</th><th>Floor</th></tr></thead>
              <tbody>
                {stock.map((s) => (
                  <tr key={s.bloodGroup}>
                    <td><a href={`/bank/inventory?group=${encodeURIComponent(s.bloodGroup)}`}><span className="blood-chip">{s.bloodGroup}</span></a></td>
                    <td>{s.available}</td>
                    <td>{s.shortfall > 0 ? <span className="status-pill status-draft">−{s.shortfall}</span> : s.floor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="panel min-w-0" aria-labelledby="bags-heading">
        <div className="page-header mb-5">
          <h2 id="bags-heading">
            Bags{groupFilter ? ` · ${groupFilter}` : ""} · {statusFilter}
          </h2>
          <form method="get" action="/bank/inventory" className="actions">
            {groupFilter ? <input type="hidden" name="group" value={groupFilter} /> : null}
            <select name="status" defaultValue={statusFilter} className="input">
              {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button type="submit" className="button">Filter</button>
            {groupFilter ? <a className="button" href="/bank/inventory">All groups</a> : null}
          </form>
        </div>
        {bags.length === 0 ? (
          <p className="empty-state">No bags match.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th>RFID</th><th>Group</th><th>Product</th><th>Collected</th><th>Expires</th><th>Status</th><th>Action</th></tr>
              </thead>
              <tbody>
                {bags.map((bag) => (
                  <tr key={bag.id}>
                    <td><code>{bag.rfidTag}</code></td>
                    <td><span className="blood-chip">{bag.bloodGroup}</span></td>
                    <td>{bloodProductLabelMap[bag.product]}</td>
                    <td>{bag.collectedAt}</td>
                    <td>{bag.expiresAt}</td>
                    <td><span className={statusClass(bag.status)}>{bag.status}</span></td>
                    <td>
                      {bag.status === "available" ? (
                        <form method="post" action="/api/bank/bags/status">
                          <input type="hidden" name="bagId" value={bag.id} />
                          <input type="hidden" name="status" value="discarded" />
                          <button type="submit" className="button">Discard</button>
                        </form>
                      ) : bag.status === "discarded" || bag.status === "expired" ? (
                        <form method="post" action="/api/bank/bags/status">
                          <input type="hidden" name="bagId" value={bag.id} />
                          <input type="hidden" name="status" value="available" />
                          <button type="submit" className="button">Restore</button>
                        </form>
                      ) : null}
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
