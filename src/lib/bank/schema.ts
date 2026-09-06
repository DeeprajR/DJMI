import { z } from "zod";
import { bloodGroupValues, bloodProductValues } from "@/lib/blood-request/draft";

const isoDate = z
  .string()
  .trim()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD");

/** A bag entered by hand or by an RFID reader. */
export const addBagSchema = z
  .object({
    rfidTag: z.string().trim().min(3).max(64),
    bloodGroup: z.enum(bloodGroupValues),
    product: z.enum(bloodProductValues).default("whole_blood"),
    collectedAt: isoDate,
    expiresAt: isoDate,
  })
  .refine((v) => v.expiresAt >= v.collectedAt, {
    message: "Expiry must not be before collection",
    path: ["expiresAt"],
  });

/** What the reader posts. `action` lets one endpoint cover stocking and discarding. */
export const scanSchema = z.object({
  rfidTag: z.string().trim().min(3).max(64),
  action: z.enum(["stock", "discard", "lookup"]).default("lookup"),
  bloodGroup: z.enum(bloodGroupValues).optional(),
  product: z.enum(bloodProductValues).optional(),
  collectedAt: isoDate.optional(),
  expiresAt: isoDate.optional(),
});

export const bagStatusSchema = z.object({
  bagId: z.string().uuid(),
  status: z.enum(["available", "discarded", "expired"]),
});

export const decisionSchema = z.object({
  bloodRequestId: z.string().uuid(),
  decision: z.enum(["approved", "partial", "declined"]),
  unitsToIssue: z.coerce.number().int().min(0).max(50).default(0),
  note: z.string().trim().max(500).optional().or(z.literal("")),
  recruitDonors: z
    .union([z.literal("on"), z.literal("true"), z.literal("false"), z.literal("")])
    .optional()
    .transform((v) => v === "on" || v === "true"),
});

export const settingsSchema = z.object({
  hospitalName: z.string().trim().min(2).max(160),
  hospitalAddress: z.string().trim().min(2).max(500),
  district: z.string().trim().min(2).max(80),
  city: z.string().trim().min(2).max(80),
  minUnitsPerGroup: z.coerce.number().int().min(0).max(500),
});

export const markConfirmationSchema = z.object({
  confirmationId: z.string().uuid(),
  status: z.enum(["completed", "no_show", "cancelled"]),
  donatedAt: isoDate.optional().or(z.literal("")),
  bagRfidTag: z.string().trim().max(64).optional().or(z.literal("")),
});

export const cancelDemandSchema = z.object({
  demandId: z.string().uuid(),
});

export const bankMessages = {
  bag_added: "Bag added to stock.",
  bag_exists: "That RFID tag is already in stock.",
  bag_updated: "Bag updated.",
  decision_saved: "Decision recorded and the doctor notified.",
  already_decided: "This request already has a decision.",
  insufficient_stock: "Not enough available bags of that group to issue.",
  settings_saved: "Settings saved.",
  demand_cancelled: "Demand withdrawn; the bot will stop recruiting on its next tick.",
  floor_raised: "Donor demand raised for every group below the floor.",
  marked: "Donor updated; the bot will thank them on its next tick.",
  invalid: "Please check the highlighted fields.",
  invalid_origin: "Request rejected: invalid origin.",
} as const;
