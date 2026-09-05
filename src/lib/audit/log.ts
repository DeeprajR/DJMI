import "server-only";

import { db } from "@/db/client";
import { auditLog } from "@/db/schema";

type AuditActorType = typeof auditLog.$inferInsert.actorType;

type WriteAuditLogInput = {
  actorType: AuditActorType;
  actorDoctorId?: string | null;
  action: string;
  entityType: string;
  entityId: string;
  metadata?: Record<string, unknown> | null;
};

function serializeMetadata(metadata: Record<string, unknown> | null | undefined): string | null {
  if (!metadata) {
    return null;
  }

  try {
    return JSON.stringify(metadata);
  } catch {
    return JSON.stringify({ serializeError: true });
  }
}

export async function writeAuditLog(input: WriteAuditLogInput): Promise<void> {
  await db.insert(auditLog).values({
    actorType: input.actorType,
    actorDoctorId: input.actorDoctorId ?? null,
    action: input.action,
    entityType: input.entityType,
    entityId: input.entityId,
    metadata: serializeMetadata(input.metadata),
  });
}

export async function writeAuditLogSafe(input: WriteAuditLogInput): Promise<void> {
  try {
    await writeAuditLog(input);
  } catch {
    // Audit logging is best-effort and must not block critical workflows.
  }
}
