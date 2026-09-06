import { NextRequest } from "next/server";
import { decideRequest } from "@/lib/bank/demand";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { decisionSchema } from "@/lib/bank/schema";

/** The bank's answer to a doctor's request: issue bags, and recruit for the rest. */
export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/requests", decisionSchema, async (data, user) => {
    const result = await decideRequest({
      bloodRequestId: data.bloodRequestId,
      decision: data.decision,
      unitsToIssue: data.unitsToIssue,
      note: data.note || null,
      recruitDonorsForShortfall: data.recruitDonors,
      decidedBy: user.id,
    });
    if (!result.ok) {
      return `error=${result.reason}`;
    }
    return "notice=decision_saved";
  });
}
