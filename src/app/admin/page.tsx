import { desc } from "drizzle-orm";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { requireAdmin } from "@/lib/auth/guard";
import { adminErrorMessages, adminSuccessMessages, userRoles } from "@/lib/admin/schema";

type AdminPageProps = {
  searchParams: Promise<{
    error?: string;
    created?: string;
    roleUpdated?: string;
    statusUpdated?: string;
  }>;
};

function successKey(params: Awaited<AdminPageProps["searchParams"]>): string | null {
  if (params.created === "1") return "created";
  if (params.roleUpdated === "1") return "role_updated";
  if (params.statusUpdated === "1") return "status_updated";
  return null;
}

function formatDateTime(date: Date): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default async function AdminPage({ searchParams }: AdminPageProps) {
  const admin = await requireAdmin();
  const params = await searchParams;

  const accounts = await db.query.doctors.findMany({
    orderBy: [desc(doctors.createdAt)],
    columns: {
      id: true,
      email: true,
      role: true,
      doctorName: true,
      doctorProvisionalReg: true,
      isActive: true,
      createdAt: true,
    },
  });

  const errorMessage = params.error ? adminErrorMessages[params.error] : null;
  const successMessage = (() => {
    const key = successKey(params);
    return key ? adminSuccessMessages[key] : null;
  })();

  const activeAdmins = accounts.filter((row) => row.role === "admin" && row.isActive).length;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <span className="role-badge role-doctor">Admin</span>
          <h1 className="page-heading">Account administration</h1>
          <p className="page-description">
            Create doctor accounts and manage role-based access. Signed in as {admin.doctorName}.
          </p>
        </div>
      </header>

      {successMessage ? (
        <div className="notice notice-success" role="status">
          {successMessage}
        </div>
      ) : null}

      {errorMessage ? (
        <div className="notice notice-error" role="alert">
          {errorMessage}
        </div>
      ) : null}

      <section className="grid min-w-0 items-start gap-6 md:grid-cols-2">
        <div className="panel min-w-0">
          <h2>Create account</h2>
          <p className="page-description">
            Accounts are provisioned here only. Self-registration stays disabled.
          </p>
          <form method="post" action="/api/admin/doctors" className="form-stack mt-5">
            <label className="field">
              Doctor name
              <input name="doctorName" type="text" required maxLength={200} className="input" />
            </label>

            <label className="field">
              Email
              <input
                name="email"
                type="email"
                required
                autoComplete="off"
                maxLength={320}
                className="input"
              />
            </label>

            <label className="field">
              Doctor Provisional Reg.
              <input
                name="doctorProvisionalReg"
                type="text"
                required
                maxLength={120}
                className="input"
              />
            </label>

            <label className="field">
              Temporary password
              <input
                name="password"
                type="password"
                required
                minLength={12}
                maxLength={200}
                autoComplete="new-password"
                className="input"
              />
              <span className="page-description">Minimum 12 characters.</span>
            </label>

            <label className="field">
              Role
              <select name="role" defaultValue="doctor" className="input">
                {userRoles.map((role) => (
                  <option key={role} value={role}>
                    {role === "admin" ? "Admin" : "Doctor"}
                  </option>
                ))}
              </select>
            </label>

            <button type="submit" className="button button-primary">
              Create account
            </button>
          </form>
        </div>

        <div className="panel min-w-0">
          <h2>Access rules</h2>
          <dl className="detail-grid mt-5">
            <div>
              <dt>Doctor</dt>
              <dd>Patients, admissions, blood requests, samples, and own profile.</dd>
            </div>
            <div>
              <dt>Admin</dt>
              <dd>Everything a doctor can do, plus this account administration panel.</dd>
            </div>
            <div>
              <dt>Active admins</dt>
              <dd>{activeAdmins}</dd>
            </div>
            <div>
              <dt>Safeguards</dt>
              <dd>
                You cannot change your own role or deactivate yourself, and the last active admin
                cannot be removed.
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="panel min-w-0">
        <h2 className="mb-5">Accounts</h2>
        <div className="table-scroll" role="region" tabIndex={0} aria-label="User accounts">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Doctor name</th>
                <th scope="col">Email</th>
                <th scope="col">Provisional Reg.</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-state">
                    No accounts found.
                  </td>
                </tr>
              ) : (
                accounts.map((account) => {
                  const isSelf = account.id === admin.id;
                  return (
                    <tr key={account.id}>
                      <td>{account.doctorName}</td>
                      <td>{account.email}</td>
                      <td>{account.doctorProvisionalReg}</td>
                      <td>
                        <span className="status-pill">{account.role}</span>
                      </td>
                      <td>
                        <span
                          className={`status-pill ${
                            account.isActive ? "status-submitted" : "status-draft"
                          }`}
                        >
                          {account.isActive ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td>{formatDateTime(account.createdAt)}</td>
                      <td>
                        {isSelf ? (
                          <span className="page-description">Your account</span>
                        ) : (
                          <div className="actions">
                            <form
                              method="post"
                              action="/api/admin/doctors/role"
                              className="actions"
                            >
                              <input type="hidden" name="doctorId" value={account.id} />
                              <input
                                type="hidden"
                                name="role"
                                value={account.role === "admin" ? "doctor" : "admin"}
                              />
                              <button type="submit" className="button">
                                {account.role === "admin" ? "Make doctor" : "Make admin"}
                              </button>
                            </form>
                            <form
                              method="post"
                              action="/api/admin/doctors/status"
                              className="actions"
                            >
                              <input type="hidden" name="doctorId" value={account.id} />
                              <input
                                type="hidden"
                                name="isActive"
                                value={account.isActive ? "false" : "true"}
                              />
                              <button type="submit" className="button">
                                {account.isActive ? "Deactivate" : "Activate"}
                              </button>
                            </form>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
