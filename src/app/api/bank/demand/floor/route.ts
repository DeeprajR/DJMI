import { NextRequest, NextResponse } from "next/server";
import { requireBankApi } from "@/lib/auth/bank-guard";
import { raiseFloorDemand } from "@/lib/bank/demand";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

/** "Keep 25 units of every group": raise donor demand for each group below the floor. */
export async function POST(request: NextRequest) {
  const back = (query: string) => NextResponse.redirect(new URL(`/bank?${query}`, request.url), 303);
  if (!isTrustedPostOrigin(request)) {
    return back("error=Request%20rejected%3A%20invalid%20origin");
  }
  const guard = await requireBankApi();
  if (!guard.ok) {
    return NextResponse.redirect(new URL(guard.reason === "unauthenticated" ? "/sign-in" : "/dashboard", request.url), 303);
  }
  const raised = await raiseFloorDemand(guard.user.id);
  const message =
    raised === 0
      ? "Every group is at its floor, or already has restocking demand open."
      : `Donor demand raised for ${raised} group${raised === 1 ? "" : "s"}. The bot will start within a minute.`;
  return back(`notice=${encodeURIComponent(message)}`);
}
