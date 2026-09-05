import { and, eq } from "drizzle-orm";
import Link from "next/link";
import Image from "next/image";
import { notFound, redirect } from "next/navigation";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { requireDoctor } from "@/lib/auth/guard";
import {
  bloodGroupValues,
  bloodProductLabelMap,
  bloodProductValues,
} from "@/lib/blood-request/draft";

type RequestDraftPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams: Promise<{
    saved?: string;
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

export default async function RequestDraftPage({ params, searchParams }: RequestDraftPageProps) {
  const doctor = await requireDoctor();
  const route = await params;
  const query = await searchParams;

  const draft = await db.query.bloodRequests.findFirst({
    where: and(eq(bloodRequests.id, route.id), eq(bloodRequests.doctorId, doctor.id)),
    with: {
      admission: {
        with: {
          patient: true,
        },
      },
    },
  });

  if (!draft) {
    notFound();
  }

  if (draft.status !== "draft") {
    redirect(`/requests/${draft.id}/review`);
  }

  const savedMessage = query.saved === "1" ? "Draft saved." : null;
  const errorMessage = errorText(query.error);

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-heading">Blood request draft</h1>
          <p className="page-description break-words">Draft ID: {draft.id}</p>
        </div>
        <Link href="/admissions" className="button">Back to admissions</Link>
      </header>

      <ol className="workflow-steps" aria-label="Request progress">
        <li aria-current="step">Draft</li>
        <li>Review</li>
        <li>Submitted</li>
      </ol>

      {savedMessage ? (
        <div className="notice notice-success" role="status">
          {savedMessage}
        </div>
      ) : null}

      {errorMessage ? (
        <div className="notice notice-error" role="alert">{errorMessage}</div>
      ) : null}

      <section className="form-panel" aria-label="Blood request details">
        <form method="post" action={`/api/requests/drafts/${draft.id}`} className="form-stack">
          <input type="hidden" name="ipNo" value={draft.admission.ipNo} />

          <label className="field">
            Name of Patient:
            <input
              type="text"
              value={draft.admission.patient.patientName}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Age of Patient:
            <input
              type="text"
              value={`${draft.admission.patient.patientAge} ${draft.admission.patient.patientAgeUnit}`}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Blood Group of Patient:
            <input
              type="text"
              value={draft.admission.patient.patientBloodGroup}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            IP No. of Patient:
            <input
              type="text"
              value={draft.admission.ipNo}
              readOnly
              className="input"
            />
          </label>

          <label className="field">
            Ward No.:
            <input
              type="text"
              value={draft.admission.wardNo}
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
              defaultValue={draft.reasonForTransfusion ?? ""}
              className="input"
            />
          </label>

          <label className="field">
            Date Needed:
            <input
              name="dateNeeded"
              type="date"
              required
              defaultValue={draft.dateNeeded ?? ""}
              className="input"
            />
          </label>

          <label className="field">
            Blood Group:
            <select
              name="requestedBloodGroup"
              required
              defaultValue={draft.requestedBloodGroup ?? ""}
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
              defaultValue={draft.product ?? ""}
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
              defaultValue={draft.units ?? ""}
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

          <div className="actions">
            <button type="submit" className="button button-primary w-full sm:w-fit">
              Save draft
            </button>
            <Link href={`/requests/${draft.id}/review`} className="button w-full sm:w-fit">
              Review
            </Link>
          </div>
        </form>
      </section>
    </main>
  );
}
