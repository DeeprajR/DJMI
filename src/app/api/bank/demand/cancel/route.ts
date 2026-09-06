import { NextRequest } from "next/server";
import { cancelDemand } from "@/lib/bank/demand";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { cancelDemandSchema } from "@/lib/bank/schema";

/** Withdraw a demand. The bot sees the status change on its next tick and closes cards. */
export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/demand", cancelDemandSchema, async (data, user) => {
    const cancelled = await cancelDemand(data.demandId, user.id);
    return cancelled ? "notice=demand_cancelled" : "error=invalid";
  });
}
