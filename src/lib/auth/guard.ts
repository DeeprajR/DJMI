import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import { getAuthSession } from "./session";

export const getRequiredSession = cache(async () => {
  const session = await getAuthSession();
  if (!session) {
    redirect("/sign-in");
  }
  return session;
});

export async function requireDoctor() {
  const session = await getRequiredSession();
  if (session.doctor.role !== "doctor" && session.doctor.role !== "admin") {
    redirect("/sign-in");
  }
  return session.doctor;
}

export async function requireAdmin() {
  const session = await getRequiredSession();
  if (session.doctor.role !== "admin") {
    redirect("/dashboard");
  }
  return session.doctor;
}
