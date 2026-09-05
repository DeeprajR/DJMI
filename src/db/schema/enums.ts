import { pgEnum } from "drizzle-orm/pg-core";

export const bloodGroupEnum = pgEnum("blood_group", [
  "A+",
  "A-",
  "B+",
  "B-",
  "AB+",
  "AB-",
  "O+",
  "O-",
]);

export const bloodProductEnum = pgEnum("blood_product", [
  "whole_blood",
  "packed_rbc",
  "platelet",
  "fresh_frozen_plasma",
  "cryopresipitate",
]);

export const requestStatusEnum = pgEnum("request_status", [
  "draft",
  "submitted",
  "cancelled",
]);

export const ageUnitEnum = pgEnum("age_unit", ["days", "months", "years"]);

export const admissionStatusEnum = pgEnum("admission_status", [
  "active",
  "discharged",
]);

export const userRoleEnum = pgEnum("user_role", ["doctor", "admin"]);

export const auditActorTypeEnum = pgEnum("audit_actor_type", [
  "doctor",
  "admin",
  "system",
]);
