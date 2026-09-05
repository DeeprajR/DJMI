import { eq } from "drizzle-orm";
import { db } from "@/db/client";
import { admissions } from "@/db/schema";

export async function getAdmissionContext(ipNo: string) {
  return db.query.admissions.findFirst({
    where: eq(admissions.ipNo, ipNo),
    with: {
      patient: true,
    },
  });
}
