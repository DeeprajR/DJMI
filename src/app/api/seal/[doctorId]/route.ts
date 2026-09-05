import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { getAuthSession } from "@/lib/auth/session";
import { readSealImage } from "@/lib/storage/seal";

type RouteParams = {
  params: Promise<{
    doctorId: string;
  }>;
};

export async function GET(_request: Request, { params }: RouteParams) {
  const session = await getAuthSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { doctorId } = await params;
  const allowed = session.doctor.role === "admin" || session.doctor.id === doctorId;
  if (!allowed) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let sealFileName: string | null | undefined = null;
  if (session.doctor.id === doctorId) {
    sealFileName = session.doctor.doctorSealPath;
  } else {
    const targetDoctor = await db.query.doctors.findFirst({
      where: eq(doctors.id, doctorId),
      columns: {
        doctorSealPath: true,
      },
    });
    sealFileName = targetDoctor?.doctorSealPath;
  }

  if (!sealFileName) {
    return NextResponse.json({ error: "Seal not found" }, { status: 404 });
  }

  try {
    const imageBuffer = await readSealImage(sealFileName);
    return new NextResponse(new Uint8Array(imageBuffer), {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json({ error: "Seal not found" }, { status: 404 });
  }
}
