import Link from "next/link";
import { requireBank } from "@/lib/auth/bank-guard";
import { bankMessages } from "@/lib/bank/schema";
import { getBankSettings } from "@/lib/bank/stock";

type Props = { searchParams: Promise<{ notice?: string; error?: string }> };

export default async function BankSettingsPage({ searchParams }: Props) {
  await requireBank();
  const params = await searchParams;
  const settings = await getBankSettings();

  const notice = params.notice ? bankMessages[params.notice as keyof typeof bankMessages] : null;
  const error = params.error ? (bankMessages[params.error as keyof typeof bankMessages] ?? params.error) : null;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Blood bank settings</h1>
          <p className="page-description">
            The hospital identity donors see on every card, and the stock floor per group.
          </p>
        </div>
        <Link className="button" href="/bank">Overview</Link>
      </header>

      {notice ? <div className="notice notice-success" role="status">{notice}</div> : null}
      {error ? <div className="notice notice-error" role="alert">{error}</div> : null}

      <section className="panel min-w-0">
        <form method="post" action="/api/bank/settings" className="form-stack">
          <label className="field">
            Hospital name
            <input name="hospitalName" type="text" required defaultValue={settings.hospitalName} className="input" />
          </label>
          <label className="field">
            Address shown to donors (include the counter or floor)
            <input name="hospitalAddress" type="text" required defaultValue={settings.hospitalAddress} className="input" />
          </label>
          <label className="field">
            District (must match the bot&apos;s district list exactly)
            <input name="district" type="text" required defaultValue={settings.district} className="input" />
          </label>
          <label className="field">
            City / town
            <input name="city" type="text" required defaultValue={settings.city} className="input" />
          </label>
          <label className="field">
            Minimum units to keep per blood group
            <input name="minUnitsPerGroup" type="number" min={0} max={500} required defaultValue={settings.minUnitsPerGroup} className="input" />
          </label>
          <div className="actions">
            <button type="submit" className="button button-primary">Save settings</button>
          </div>
        </form>
        <p className="page-description mt-5">
          Changing these affects new donor demand only; demand already raised keeps the details it was raised with.
        </p>
      </section>
    </main>
  );
}
