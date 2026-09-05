import { and, eq } from "drizzle-orm";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { requireDoctor } from "@/lib/auth/guard";
import { bloodProductLabelMap } from "@/lib/blood-request/draft";

type RequestViewPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams: Promise<{
    sampleAdded?: string;
    error?: string;
  }>;
};

function statusBadgeClass(status: string): string {
  if (status === "submitted") {
    return "status-submitted";
  }
  if (status === "draft") {
    return "status-draft";
  }
  return "";
}

export default async function RequestViewPage({ params, searchParams }: RequestViewPageProps) {
  const doctor = await requireDoctor();
  const route = await params;
  const query = await searchParams;

  const request = await db.query.bloodRequests.findFirst({
    where: and(eq(bloodRequests.id, route.id), eq(bloodRequests.doctorId, doctor.id)),
    with: {
      admission: {
        with: {
          patient: true,
        },
      },
      doctor: true,
      samples: {
        with: {
          collectedBy: true,
        },
        orderBy: (table, { desc }) => [desc(table.collectedAt)],
      },
    },
  });

  if (!request) {
    notFound();
  }

  const patientName = request.patientNameSnapshot || request.admission.patient.patientName;
  const patientAgeValue = request.patientAgeSnapshot ?? request.admission.patient.patientAge;
  const patientAgeUnit = request.patientAgeUnitSnapshot || request.admission.patient.patientAgeUnit;
  const patientBloodGroup =
    request.patientBloodGroupSnapshot || request.admission.patient.patientBloodGroup;
  const wardNo = request.wardNoSnapshot || request.admission.wardNo;
  const doctorName = request.doctorNameSnapshot || request.doctor.doctorName;
  const doctorReg =
    request.doctorProvisionalRegSnapshot || request.doctor.doctorProvisionalReg;
  const doctorSealAvailable = !!request.doctor.doctorSealPath;
  const sampleAddedMessage = query.sampleAdded === "1" ? "Blood sample associated." : null;

  let sampleError: string | null = null;
  if (query.error === "requires_submitted") {
    sampleError = "Samples can be associated only after submission.";
  } else if (query.error === "invalid_sample") {
    sampleError = "Invalid sample details.";
  } else if (query.error === "invalid_collected_at") {
    sampleError = "Invalid collection date and time.";
  } else if (query.error === "duplicate_sample") {
    sampleError = "Sample identifier already exists.";
  }

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-heading">Blood request</h1>
          <p className="page-description break-words">Internal ID: {request.id}</p>
        </div>
        <div className="actions">
          {request.status === "draft" ? (
            <Link
              href={`/requests/${request.id}`}
              className="button"
            >
              Edit draft
            </Link>
          ) : null}
        </div>
      </header>

      <ol className="workflow-steps" aria-label="Request progress">
        <li aria-current={request.status === "draft" ? "step" : undefined}>Draft</li>
        <li>Review</li>
        <li aria-current={request.status === "submitted" ? "step" : undefined}>Submitted</li>
      </ol>

      <section className="panel" aria-label="Blood request details">
        <div className="actions mb-6">
          <span
            className={`status-pill ${statusBadgeClass(
              request.status
            )}`}
          >
            {request.status}
          </span>
          <span className="page-description">Request ID: {request.requestId || "Pending"}</span>
        </div>

        <dl className="detail-grid">
          <div>
            <dt className="font-medium">Name of Patient:</dt>
            <dd>{patientName}</dd>
          </div>
          <div>
            <dt className="font-medium">Age of Patient:</dt>
            <dd>
              {patientAgeValue} {patientAgeUnit}
            </dd>
          </div>
          <div>
            <dt className="font-medium">Blood Group of Patient:</dt>
            <dd><span className="blood-chip">{patientBloodGroup}</span></dd>
          </div>
          <div>
            <dt className="font-medium">IP No. of Patient:</dt>
            <dd>{request.ipNo}</dd>
          </div>
          <div>
            <dt className="font-medium">Ward No.:</dt>
            <dd>{wardNo}</dd>
          </div>
          <div>
            <dt className="font-medium">Reason for transfusion:</dt>
            <dd>{request.reasonForTransfusion || "-"}</dd>
          </div>
          <div>
            <dt className="font-medium">Date Needed:</dt>
            <dd>{request.dateNeeded || "-"}</dd>
          </div>
          <div>
            <dt className="font-medium">Blood Group:</dt>
            <dd><span className="blood-chip">{request.requestedBloodGroup || "-"}</span></dd>
          </div>
          <div>
            <dt className="font-medium">Request: Whole Blood, Packed RBC, Platelet, Fresh Frozen Plasma, Cryopresipitate</dt>
            <dd>{request.product ? bloodProductLabelMap[request.product] : "-"}</dd>
          </div>
          <div>
            <dt className="font-medium">No. of Units:</dt>
            <dd>{request.units ?? "-"}</dd>
          </div>
          <div>
            <dt className="font-medium">Doctor name:</dt>
            <dd>{doctorName}</dd>
          </div>
          <div>
            <dt className="font-medium">Doctor Provisional Reg.:</dt>
            <dd>{doctorReg}</dd>
          </div>
          <div>
            <dt className="font-medium">Doctor Seal:</dt>
            <dd>
              {doctorSealAvailable ? (
                <Image
                  src={`/api/seal/${request.doctorId}`}
                  alt="Doctor seal"
                  width={300}
                  height={140}
                  unoptimized
                  className="panel mt-2 h-auto max-h-36 max-w-full object-contain"
                />
              ) : (
                "No seal uploaded."
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel grid min-w-0 gap-6" aria-labelledby="samples-heading">
        <h2 id="samples-heading" className="text-2xl font-semibold">Associated blood samples</h2>

        {sampleAddedMessage ? (
          <div className="notice notice-success" role="status">
            {sampleAddedMessage}
          </div>
        ) : null}

        {sampleError ? (
          <div className="notice notice-error" role="alert">
            {sampleError}
          </div>
        ) : null}

        {request.status === "submitted" ? (
          <form method="post" action={`/api/requests/${request.id}/samples`} className="form-stack mx-auto w-full max-w-[480px]">
            <label className="field">
              Sample Identifier
              <input
                name="sampleIdentifier"
                type="text"
                required
                className="input"
              />
            </label>
            <label className="field">
              Collected At
              <input
                name="collectedAt"
                type="datetime-local"
                required
                className="input"
              />
            </label>
            <label className="field">
              Collected By
              <input
                type="text"
                value={doctor.doctorName}
                readOnly
                className="input"
              />
            </label>
            <button
              type="submit"
              className="button button-primary w-full sm:w-fit"
            >
              Associate sample
            </button>
          </form>
        ) : (
          <p className="notice notice-info" role="status">Submit the request to associate blood samples.</p>
        )}

        <div className="table-scroll" tabIndex={0} role="region" aria-label="Associated blood samples table">
          <table className="data-table min-w-[700px]">
            <caption className="sr-only">Associated blood samples and collection details</caption>
            <thead>
              <tr>
                <th scope="col">Sample Identifier</th>
                <th scope="col">Collected At</th>
                <th scope="col">Collected By</th>
                <th scope="col">Recorded At</th>
              </tr>
            </thead>
            <tbody>
              {request.samples.length === 0 ? (
                <tr>
                  <td colSpan={4} className="empty-state">
                    No samples associated.
                  </td>
                </tr>
              ) : (
                request.samples.map((sample) => (
                  <tr key={sample.id}>
                    <td>{sample.sampleIdentifier}</td>
                    <td>{sample.collectedAt.toISOString()}</td>
                    <td>
                      {sample.collectedBy.doctorName} ({sample.collectedBy.doctorProvisionalReg})
                    </td>
                    <td>{sample.createdAt.toISOString()}</td>
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
