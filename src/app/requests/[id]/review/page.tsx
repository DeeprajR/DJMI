import { and, eq } from "drizzle-orm";
import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { requireDoctor } from "@/lib/auth/guard";
import { bloodProductLabelMap } from "@/lib/blood-request/draft";

type RequestReviewPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams: Promise<{
    submitted?: string;
    error?: string;
  }>;
};

function reviewErrorText(code?: string): string | null {
  if (code === "incomplete") {
    return "Draft is incomplete. Fill all required fields before submit.";
  }
  if (code === "admission_not_found") {
    return "Admission context was not found for this request.";
  }
  if (code === "already_submitted") {
    return "Request is already submitted and cannot be edited.";
  }
  if (code === "submit_failed") {
    return "Submit failed. Please retry.";
  }
  return null;
}

export default async function RequestReviewPage({ params, searchParams }: RequestReviewPageProps) {
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
    },
  });

  if (!request) {
    notFound();
  }

  const submitted = query.submitted === "1";
  const errorMessage = reviewErrorText(query.error);
  const doctorName = request.doctorNameSnapshot || doctor.doctorName;
  const doctorReg = request.doctorProvisionalRegSnapshot || doctor.doctorProvisionalReg;
  const doctorSealAvailable = !!doctor.doctorSealPath;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-heading">Review blood request</h1>
          <p className="page-description break-words">Draft ID: {request.id}</p>
        </div>
        <div className="actions">
          {request.status === "draft" ? (
            <Link
              href={`/requests/${request.id}`}
              className="button"
            >
              Back to draft
            </Link>
          ) : null}
          {request.status === "submitted" ? (
            <Link
              href={`/requests/${request.id}/view`}
              className="button"
            >
              View request
            </Link>
          ) : null}
        </div>
      </header>

      <ol className="workflow-steps" aria-label="Request progress">
        <li>Draft</li>
        <li aria-current={request.status === "draft" ? "step" : undefined}>Review</li>
        <li aria-current={request.status === "submitted" ? "step" : undefined}>Submitted</li>
      </ol>

      {submitted ? (
        <div className="notice notice-success" role="status">
          Submitted successfully. Request ID: {request.requestId}
        </div>
      ) : null}

      {errorMessage ? (
        <div className="notice notice-error" role="alert">{errorMessage}</div>
      ) : null}

      {request.status === "submitted" && request.requestId ? (
        <section className="notice notice-info" role="status">
          Request ID: {request.requestId}
        </section>
      ) : null}

      <section className="panel" aria-label="Blood request details">
        <dl className="detail-grid">
          <div>
            <dt className="font-medium">Name of Patient:</dt>
            <dd>{request.admission.patient.patientName}</dd>
          </div>
          <div>
            <dt className="font-medium">Age of Patient:</dt>
            <dd>
              {request.admission.patient.patientAge} {request.admission.patient.patientAgeUnit}
            </dd>
          </div>
          <div>
            <dt className="font-medium">Blood Group of Patient:</dt>
            <dd><span className="blood-chip">{request.admission.patient.patientBloodGroup}</span></dd>
          </div>
          <div>
            <dt className="font-medium">IP No. of Patient:</dt>
            <dd>{request.admission.ipNo}</dd>
          </div>
          <div>
            <dt className="font-medium">Ward No.:</dt>
            <dd>{request.admission.wardNo}</dd>
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
                  src={`/api/seal/${doctor.id}`}
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

      {request.status === "draft" ? (
        <form method="post" action={`/api/requests/submit/${request.id}`} className="actions">
          <button
            type="submit"
            className="button button-primary w-full sm:w-fit"
          >
            Submit blood request
          </button>
        </form>
      ) : null}
    </main>
  );
}
