import { relations, sql } from "drizzle-orm";
import {
  bigint,
  boolean,
  check,
  date,
  index,
  integer,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from "drizzle-orm/pg-core";
import {
  admissionStatusEnum,
  ageUnitEnum,
  auditActorTypeEnum,
  bloodGroupEnum,
  bloodProductEnum,
  requestStatusEnum,
  userRoleEnum,
} from "./enums";

export const doctors = pgTable(
  "doctors",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    email: varchar("email", { length: 320 }).notNull(),
    passwordHash: text("password_hash").notNull(),
    role: userRoleEnum("role").notNull().default("doctor"),
    doctorName: text("doctor_name").notNull(),
    doctorProvisionalReg: text("doctor_provisional_reg").notNull(),
    doctorSealPath: text("doctor_seal_path"),
    isActive: boolean("is_active").notNull().default(true),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    uniqueIndex("doctors_email_uq").on(table.email),
    uniqueIndex("doctors_provisional_reg_uq").on(table.doctorProvisionalReg),
  ]
);

export const sessions = pgTable(
  "sessions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    doctorId: uuid("doctor_id")
      .notNull()
      .references(() => doctors.id, { onDelete: "cascade" }),
    tokenHash: text("token_hash").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    revokedAt: timestamp("revoked_at", { withTimezone: true }),
  },
  (table) => [
    uniqueIndex("sessions_token_hash_uq").on(table.tokenHash),
    index("sessions_doctor_id_idx").on(table.doctorId),
    index("sessions_expires_at_idx").on(table.expiresAt),
  ]
);

export const authRateLimits = pgTable(
  "auth_rate_limits",
  {
    scope: text("scope").notNull(),
    key: text("key").notNull(),
    attempts: integer("attempts").notNull().default(0),
    windowStartedAt: timestamp("window_started_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    blockedUntil: timestamp("blocked_until", { withTimezone: true }),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    primaryKey({ columns: [table.scope, table.key], name: "auth_rate_limits_pk" }),
    check(
      "auth_rate_limits_scope_check",
      sql`${table.scope} IN ('login_ip', 'login_account')`
    ),
    check("auth_rate_limits_attempts_non_negative", sql`${table.attempts} >= 0`),
    index("auth_rate_limits_blocked_until_idx").on(table.blockedUntil),
  ]
);

export const patients = pgTable(
  "patients",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    patientName: text("patient_name").notNull(),
    patientAge: integer("patient_age").notNull(),
    patientAgeUnit: ageUnitEnum("patient_age_unit").notNull().default("years"),
    patientBloodGroup: bloodGroupEnum("patient_blood_group").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    check("patients_age_non_negative", sql`${table.patientAge} >= 0`),
    index("patients_name_idx").on(table.patientName),
  ]
);

export const admissions = pgTable(
  "admissions",
  {
    ipNo: text("ip_no").primaryKey(),
    patientId: uuid("patient_id")
      .notNull()
      .references(() => patients.id, { onDelete: "restrict" }),
    wardNo: text("ward_no").notNull(),
    admittedAt: timestamp("admitted_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    dischargedAt: timestamp("discharged_at", { withTimezone: true }),
    admissionStatus: admissionStatusEnum("admission_status")
      .notNull()
      .default("active"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("admissions_patient_id_idx").on(table.patientId),
    index("admissions_status_idx").on(table.admissionStatus),
  ]
);

export const bloodRequests = pgTable(
  "blood_requests",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    requestId: text("request_id"),
    ipNo: text("ip_no")
      .notNull()
      .references(() => admissions.ipNo, { onDelete: "restrict" }),
    patientNameSnapshot: text("patient_name_snapshot"),
    patientAgeSnapshot: integer("patient_age_snapshot"),
    patientAgeUnitSnapshot: ageUnitEnum("patient_age_unit_snapshot"),
    patientBloodGroupSnapshot: bloodGroupEnum("patient_blood_group_snapshot"),
    wardNoSnapshot: text("ward_no_snapshot"),
    reasonForTransfusion: text("reason_for_transfusion"),
    dateNeeded: date("date_needed"),
    requestedBloodGroup: bloodGroupEnum("requested_blood_group"),
    product: bloodProductEnum("product"),
    units: integer("units"),
    doctorId: uuid("doctor_id")
      .notNull()
      .references(() => doctors.id, { onDelete: "restrict" }),
    doctorNameSnapshot: text("doctor_name_snapshot"),
    doctorProvisionalRegSnapshot: text("doctor_provisional_reg_snapshot"),
    doctorSealPathSnapshot: text("doctor_seal_path_snapshot"),
    status: requestStatusEnum("status").notNull().default("draft"),
    submittedAt: timestamp("submitted_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    uniqueIndex("blood_requests_request_id_uq")
      .on(table.requestId)
      .where(sql`${table.requestId} IS NOT NULL`),
    index("blood_requests_ip_no_idx").on(table.ipNo),
    index("blood_requests_doctor_id_idx").on(table.doctorId),
    index("blood_requests_status_idx").on(table.status),
    check("blood_requests_units_positive", sql`${table.units} IS NULL OR ${table.units} > 0`),
    check(
      "blood_requests_submitted_consistency",
      sql`(${table.status} <> 'submitted'::request_status) OR (${table.requestId} IS NOT NULL AND ${table.submittedAt} IS NOT NULL)`
    ),
  ]
);

export const bloodSamples = pgTable(
  "blood_samples",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    bloodRequestId: uuid("blood_request_id")
      .notNull()
      .references(() => bloodRequests.id, { onDelete: "cascade" }),
    sampleIdentifier: text("sample_identifier").notNull(),
    collectedAt: timestamp("collected_at", { withTimezone: true }).notNull(),
    collectedByDoctorId: uuid("collected_by_doctor_id")
      .notNull()
      .references(() => doctors.id, { onDelete: "restrict" }),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    uniqueIndex("blood_samples_identifier_uq").on(table.sampleIdentifier),
    index("blood_samples_request_id_idx").on(table.bloodRequestId),
  ]
);

export const bloodRequestCounters = pgTable(
  "blood_request_counters",
  {
    requestYear: integer("request_year").primaryKey(),
    currentValue: bigint("current_value", { mode: "number" }).notNull().default(0),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [check("blood_request_counters_non_negative", sql`${table.currentValue} >= 0`)]
);

export const auditLog = pgTable(
  "audit_log",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    actorType: auditActorTypeEnum("actor_type").notNull(),
    actorDoctorId: uuid("actor_doctor_id").references(() => doctors.id, {
      onDelete: "set null",
    }),
    action: text("action").notNull(),
    entityType: text("entity_type").notNull(),
    entityId: text("entity_id").notNull(),
    metadata: text("metadata"),
    occurredAt: timestamp("occurred_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("audit_log_occurred_at_idx").on(table.occurredAt),
    index("audit_log_entity_idx").on(table.entityType, table.entityId),
  ]
);

export const doctorsRelations = relations(doctors, ({ many }) => ({
  sessions: many(sessions),
  bloodRequests: many(bloodRequests),
  collectedSamples: many(bloodSamples),
  auditEvents: many(auditLog),
}));

export const sessionsRelations = relations(sessions, ({ one }) => ({
  doctor: one(doctors, {
    fields: [sessions.doctorId],
    references: [doctors.id],
  }),
}));

export const patientsRelations = relations(patients, ({ many }) => ({
  admissions: many(admissions),
}));

export const admissionsRelations = relations(admissions, ({ one, many }) => ({
  patient: one(patients, {
    fields: [admissions.patientId],
    references: [patients.id],
  }),
  bloodRequests: many(bloodRequests),
}));

export const bloodRequestsRelations = relations(bloodRequests, ({ one, many }) => ({
  admission: one(admissions, {
    fields: [bloodRequests.ipNo],
    references: [admissions.ipNo],
  }),
  doctor: one(doctors, {
    fields: [bloodRequests.doctorId],
    references: [doctors.id],
  }),
  samples: many(bloodSamples),
}));

export const bloodSamplesRelations = relations(bloodSamples, ({ one }) => ({
  bloodRequest: one(bloodRequests, {
    fields: [bloodSamples.bloodRequestId],
    references: [bloodRequests.id],
  }),
  collectedBy: one(doctors, {
    fields: [bloodSamples.collectedByDoctorId],
    references: [doctors.id],
  }),
}));

export const auditLogRelations = relations(auditLog, ({ one }) => ({
  actorDoctor: one(doctors, {
    fields: [auditLog.actorDoctorId],
    references: [doctors.id],
  }),
}));
