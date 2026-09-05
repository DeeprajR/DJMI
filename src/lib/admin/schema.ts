import { z } from "zod";

export const userRoles = ["doctor", "admin"] as const;

export const createDoctorSchema = z.object({
  email: z.string().trim().toLowerCase().email().max(320),
  password: z.string().min(12).max(200),
  doctorName: z.string().trim().min(1).max(200),
  doctorProvisionalReg: z.string().trim().min(1).max(120),
  role: z.enum(userRoles),
});

export const updateRoleSchema = z.object({
  doctorId: z.string().uuid(),
  role: z.enum(userRoles),
});

export const updateStatusSchema = z.object({
  doctorId: z.string().uuid(),
  isActive: z.enum(["true", "false"]).transform((value) => value === "true"),
});

export const adminErrorMessages: Record<string, string> = {
  invalid_origin: "This request could not be verified. Reload the page and try again.",
  invalid_account: "Check the account details. Passwords must be at least 12 characters.",
  duplicate_account: "An account already exists with that email or provisional registration.",
  invalid_role: "Select a valid role.",
  invalid_status: "Select a valid account status.",
  account_not_found: "That account no longer exists.",
  self_role_change: "You cannot change your own role.",
  self_deactivate: "You cannot deactivate your own account.",
  last_admin: "At least one active admin must remain.",
};

export const adminSuccessMessages: Record<string, string> = {
  created: "Doctor account created.",
  role_updated: "Role updated.",
  status_updated: "Account status updated.",
};
