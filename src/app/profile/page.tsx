import Image from "next/image";
import { requireDoctor } from "@/lib/auth/guard";

type ProfilePageProps = {
  searchParams: Promise<{
    updated?: string;
    error?: string;
  }>;
};

function errorText(code?: string): string | null {
  if (code === "missing_file") {
    return "Please choose a PNG file.";
  }
  if (code === "invalid_type") {
    return "Only PNG files are allowed.";
  }
  if (code === "upload_failed") {
    return "Upload failed. Please retry.";
  }
  return null;
}

export default async function ProfilePage({ searchParams }: ProfilePageProps) {
  const doctor = await requireDoctor();
  const params = await searchParams;
  const message = params.updated === "1" ? "Seal updated." : null;
  const error = errorText(params.error);
  const previewToken = params.updated === "1" ? "1" : "0";

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Doctor profile</h1>
          <p className="page-description">
            Identity fields are account-controlled and used as trusted request data.
          </p>
        </div>
      </header>

      <section className="panel min-w-0" aria-label="Doctor identity">
        <dl className="detail-grid break-words">
          <div>
            <dt>Doctor name</dt>
            <dd>{doctor.doctorName}</dd>
          </div>
          <div>
            <dt>Doctor Provisional Reg.</dt>
            <dd>
              {doctor.doctorProvisionalReg}
            </dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{doctor.email}</dd>
          </div>
        </dl>
      </section>

      <section className="form-panel min-w-0">
        <h2>Doctor seal (PNG)</h2>
        <p id="seal-help" className="page-description">Upload a PNG seal image up to 1MB.</p>

        {message ? (
          <div className="notice notice-success mt-5" role="status">
            {message}
          </div>
        ) : null}

        {error ? (
          <div className="notice notice-error mt-5" role="alert">
            {error}
          </div>
        ) : null}

        <form method="post" action="/api/doctor/seal" encType="multipart/form-data" className="form-stack mt-5">
          <label className="field">
            Seal image
            <input
              name="seal"
              type="file"
              accept="image/png"
              required
              aria-describedby="seal-help"
              className="input min-w-0 max-w-full"
            />
          </label>
          <button
            type="submit"
            className="button button-primary"
          >
            Upload seal
          </button>
        </form>

        <div className="panel mt-6 min-w-0">
          <p className="page-description">Current seal preview</p>
          {doctor.doctorSealPath ? (
            <Image
              src={`/api/seal/${doctor.id}?v=${previewToken}`}
              alt="Doctor seal"
              width={320}
              height={160}
              unoptimized
              className="mt-4 h-auto max-h-40 max-w-full object-contain"
            />
          ) : (
            <p className="empty-state">No seal uploaded.</p>
          )}
        </div>
      </section>
    </main>
  );
}
