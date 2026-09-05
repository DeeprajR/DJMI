import { z } from "zod";

export const bloodGroupValues = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] as const;

export const bloodProductValues = [
  "whole_blood",
  "packed_rbc",
  "platelet",
  "fresh_frozen_plasma",
  "cryopresipitate",
] as const;

export const bloodProductLabelMap: Record<(typeof bloodProductValues)[number], string> = {
  whole_blood: "Whole Blood",
  packed_rbc: "Packed RBC",
  platelet: "Platelet",
  fresh_frozen_plasma: "Fresh Frozen Plasma",
  cryopresipitate: "Cryopresipitate",
};

export const draftRequestSchema = z.object({
  ipNo: z.string().trim().min(1).max(64),
  reasonForTransfusion: z.string().trim().min(1).max(2000),
  dateNeeded: z.string().trim().min(1),
  requestedBloodGroup: z.enum(bloodGroupValues),
  product: z.enum(bloodProductValues),
  units: z.coerce.number().int().min(1).max(20),
});

export type DraftRequestInput = z.infer<typeof draftRequestSchema>;
