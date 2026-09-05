import Link from "next/link";
import Image from "next/image";
import { requireDoctor } from "@/lib/auth/guard";
import { getAdmissionContext } from "@/lib/blood-request/context";
import {
  bloodGroupValues,
  bloodProductLabelMap,
  bloodProductValues,
} from "@/lib/blood-request/draft";

type NewRequestPageProps = {
  searchParams: Promise<{
    ipNo?: string;
    error?: string;
  }>;
};

function errorText(code?: string): string | null {
  if (code === "invalid") {
    return "Invalid draft request input.";
  }
  if (code === "admission_not_found") {
    return "Admission was not found for the provided IP No.";
  }
  return null;
}

export default async function NewRequestPage({ searchParams }: NewRequestPageProps) {
  const doctor = await requireDoctor();
  const params = await searchParams;
  const ipNo = (params.ipNo || "").trim();
  const error = errorText(params.error);

  if (!ipNo) {
    return (
      <main id="main-content" tabIndex={-1} className="page">
        <header className="page-header">
          <h1 className="page-heading">Create blood request draft</h1>
        </header>
        <ol className="workflow-steps" aria-label="Request progress">
          <li aria-current="step">Draft</li>
          <li>Review</li>
          <li>Submitted</li>
        </ol>
        <section className="notice notice-warning" role="status">
          Select an admission first to create a blood request.
        </section>
        <Link
          href="/admissions"
          className="button w-fit"
        >
          Go to admissions
        </Link>
      </main>
    );
  }

  const admission = await getAdmissionContext(ipNo);
  if (!admission) {
    return (
      <main id="main-content" tabIndex={-1} className="page">
        <header className="page-header">
          <h1 className="page-heading">Create blood request draft</h1>
        </header>
        <ol className="workflow-steps" aria-label="Request progress">
          <li aria-current="step">Draft</li>
          <li>Review</li>
          <li>Submitted</li>
        </ol>
        <section className="notice notice-error" role="alert">
          Admission not found for IP No. {ipNo}.
        </section>
        <Link
          href="/admissions"
          className="button w-fit"
        >
          Back to admissions
        </Link>
      </main>
    );
  }

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div>
          <h1 className="page-heading">Create blood request draft</h1>
          <p className="page-description">Admission context is locked from IP No. selection.</p>
        </div>
        <Link href="/admissions" className="button">Back to admissions</Link>
      </header>

      <ol className="workflow-steps" aria-label="Request progress">
        <li aria-current="step">Draft</li>
        <li>Review</li>
        <li>Submitted</li>
      </ol>

      {error ? (
        <div className="notice notice-error" role="alert">{error}</div>
      ) : null}

      <section className="form-panel" aria-label="Blood request details">
        <form method="post" action="/api/requests/drafts" className="form-stack">
          <input type="hidden" name="ipNo" value={admission.ipNo} />

          <label className="field">
            Name of Patient:
            <input
              type="text"
              value={admission.patient.patientName}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Age of Patient:
            <input
              type="text"
              value={`${admission.patient.patientAge} ${admission.patient.patientAgeUnit}`}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Blood Group of Patient:
            <input
              type="text"
              value={admission.patient.patientBloodGroup}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            IP No. of Patient:
            <input
              type="text"
              value={admission.ipNo}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Ward No.:
            <input
              type="text"
              value={admission.wardNo}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Reason for transfusion:
            <textarea
              name="reasonForTransfusion"
              required
              rows={3}
              className="input"
            />
          </label>

          <label className="field">
            Date Needed:
            <input
              name="dateNeeded"
              type="date"
              required
              className="input"
            />
          </label>

          <label className="field">
            Blood Group:
            <select
              name="requestedBloodGroup"
              required
              defaultValue=""
              className="input"
            >
              <option value="" disabled>
                Select blood group
              </option>
              {bloodGroupValues.map((group) => (
                <option key={group} value={group}>
                  {group}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            Request: Whole Blood, Packed RBC, Platelet, Fresh Frozen Plasma, Cryopresipitate
            <select
              name="product"
              required
              defaultValue=""
              className="input"
            >
              <option value="" disabled>
                Select product
              </option>
              {bloodProductValues.map((product) => (
                <option key={product} value={product}>
                  {bloodProductLabelMap[product]}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            No. of Units:
            <input
              name="units"
              type="number"
              min={1}
              required
              className="input"
            />
          </label>

          <label className="field">
            Doctor name:
            <input
              type="text"
              value={doctor.doctorName}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Doctor Provisional Reg.:
            <input
              type="text"
              value={doctor.doctorProvisionalReg}
              readOnly
              className="input"
            />
          </label>

          <div className="field">
            <p>Doctor Seal:</p>
            {doctor.doctorSealPath ? (
              <Image
                src={`/api/seal/${doctor.id}`}
                alt="Doctor seal"
                width={320}
                height={160}
                unoptimized
                className="panel h-auto max-h-40 max-w-full object-contain"
              />
            ) : (
              <p className="notice notice-info" role="status">
                No seal uploaded.
              </p>
            )}
          </div>

          <button
            type="submit"
            className="button button-primary w-full sm:w-fit"
          >
            Save draft
          </button>
        </form>
      </section>
    </main>
  );
}
