/**
 * Module 2 (blood bank) tables, and the contract between the bank and the donor bot.
 *
 * Ownership, so nobody writes a column they should not:
 *
 *   bank_settings, blood_bags, bank_decisions   — written by Module 2 only
 *   donor_demand                                 — created by Module 2; the bot fills in
 *                                                  bot_* and the *_units progress columns
 *   donor_demand_confirmations                   — created by the bot when a donor is
 *                                                  confirmed; the bank sets donated_at /
 *                                                  status when the person actually gives
 *
 * The bot keeps its own tables (donors, waves, questionnaire answers) in the
 * `donor_bot` Postgres schema; nothing here references them. These two shared tables
 * are the whole integration.
 */

import { relations, sql } from "drizzle-orm";
import {
  bigint,
  check,
  date,
  index,
  integer,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { bloodGroupEnum, bloodProductEnum } from "./enums";
import { bloodRequests, doctors } from "./tables";

export const bagStatusEnum = pgEnum("bag_status", [
  "available",
  "reserved",
  "issued",
  "discarded",
  "expired",
]);

export const bankDecisionEnum = pgEnum("bank_decision", ["approved", "partial", "declined"]);

export const demandTriggerEnum = pgEnum("demand_trigger", ["request_shortfall", "stock_floor"]);

export const demandStatusEnum = pgEnum("demand_status", [
  "open",
  "fulfilled", // enough donors confirmed; the bot has stopped recruiting
  "completed", // every unit collected at the counter
  "cancelled",
  "expired",
]);

export const confirmationStatusEnum = pgEnum("confirmation_status", [
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
]);

/** One row. Hospital identity for donor cards and the stock floor per group. */
export const bankSettings = pgTable(
  "bank_settings",
  {
    id: integer("id").primaryKey().default(1),
    hospitalName: text("hospital_name").notNull(),
    hospitalAddress: text("hospital_address").notNull(),
    district: text("district").notNull(),
    city: text("city").notNull(),
    minUnitsPerGroup: integer("min_units_per_group").notNull().default(25),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
    updatedBy: uuid("updated_by").references(() => doctors.id, { onDelete: "set null" }),
  },
  (table) => [
    check("bank_settings_singleton", sql`${table.id} = 1`),
    check("bank_settings_floor_non_negative", sql`${table.minUnitsPerGroup} >= 0`),
  ]
);

/** One physical bag. The RFID tag is the bag's identity; a reader or a person types it. */
export const bloodBags = pgTable(
  "blood_bags",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    rfidTag: text("rfid_tag").notNull(),
    bloodGroup: bloodGroupEnum("blood_group").notNull(),
    product: bloodProductEnum("product").notNull().default("whole_blood"),
    collectedAt: date("collected_at").notNull(),
    expiresAt: date("expires_at").notNull(),
    status: bagStatusEnum("status").notNull().default("available"),
    issuedToRequestId: uuid("issued_to_request_id").references(() => bloodRequests.id, {
      onDelete: "set null",
    }),
    issuedAt: timestamp("issued_at", { withTimezone: true }),
    addedBy: uuid("added_by").references(() => doctors.id, { onDelete: "set null" }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("blood_bags_rfid_tag_uq").on(table.rfidTag),
    index("blood_bags_group_status_idx").on(table.bloodGroup, table.status),
    index("blood_bags_expires_at_idx").on(table.expiresAt),
    check("blood_bags_expiry_after_collection", sql`${table.expiresAt} >= ${table.collectedAt}`),
  ]
);

/** The bank's answer to a doctor's submitted request. One per request. */
export const bankDecisions = pgTable(
  "bank_decisions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    bloodRequestId: uuid("blood_request_id")
      .notNull()
      .references(() => bloodRequests.id, { onDelete: "cascade" }),
    decision: bankDecisionEnum("decision").notNull(),
    unitsRequested: integer("units_requested").notNull(),
    unitsIssued: integer("units_issued").notNull().default(0),
    note: text("note"),
    decidedBy: uuid("decided_by").references(() => doctors.id, { onDelete: "set null" }),
    decidedAt: timestamp("decided_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("bank_decisions_request_uq").on(table.bloodRequestId),
    check("bank_decisions_units_non_negative", sql`${table.unitsIssued} >= 0`),
    check(
      "bank_decisions_issued_within_requested",
      sql`${table.unitsIssued} <= ${table.unitsRequested}`
    ),
  ]
);

/**
 * Demand handed to the donor bot. Created by the bank when a request cannot be met
 * from stock, or when a group falls below the floor. The bot polls for rows with
 * status = 'open' and bot_public_id IS NULL, and reports progress back here.
 */
export const donorDemand = pgTable(
  "donor_demand",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    trigger: demandTriggerEnum("trigger").notNull(),
    bloodRequestId: uuid("blood_request_id").references(() => bloodRequests.id, {
      onDelete: "set null",
    }),
    bloodGroup: bloodGroupEnum("blood_group").notNull(),
    product: bloodProductEnum("product").notNull().default("whole_blood"),
    units: integer("units").notNull(),
    dateNeeded: date("date_needed").notNull(),
    // Snapshotted from bank_settings so a later settings edit does not rewrite history.
    hospitalName: text("hospital_name").notNull(),
    hospitalAddress: text("hospital_address").notNull(),
    district: text("district").notNull(),
    city: text("city").notNull(),
    notes: text("notes"),
    status: demandStatusEnum("status").notNull().default("open"),
    // --- written by the bot ---
    botPublicId: text("bot_public_id"),
    botImportedAt: timestamp("bot_imported_at", { withTimezone: true }),
    confirmedUnits: integer("confirmed_units").notNull().default(0),
    waitlistedUnits: integer("waitlisted_units").notNull().default(0),
    completedUnits: integer("completed_units").notNull().default(0),
    notifiedDonors: integer("notified_donors").notNull().default(0),
    // ---
    createdBy: uuid("created_by").references(() => doctors.id, { onDelete: "set null" }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
    closedAt: timestamp("closed_at", { withTimezone: true }),
  },
  (table) => [
    uniqueIndex("donor_demand_bot_public_id_uq")
      .on(table.botPublicId)
      .where(sql`${table.botPublicId} IS NOT NULL`),
    index("donor_demand_status_idx").on(table.status),
    index("donor_demand_request_idx").on(table.bloodRequestId),
    check("donor_demand_units_positive", sql`${table.units} > 0`),
  ]
);

/**
 * A donor the bot has confirmed for a demand. The roster the counter works from.
 * The bank marks the row completed (with donated_at) when the person gives blood;
 * the bot notices, updates the donor's cooldown and sends the thank-you.
 */
export const donorDemandConfirmations = pgTable(
  "donor_demand_confirmations",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    demandId: uuid("demand_id")
      .notNull()
      .references(() => donorDemand.id, { onDelete: "cascade" }),
    telegramUserId: bigint("telegram_user_id", { mode: "number" }).notNull(),
    donorName: text("donor_name"),
    donorPhone: text("donor_phone"),
    bloodGroup: bloodGroupEnum("blood_group"),
    status: confirmationStatusEnum("status").notNull().default("confirmed"),
    confirmedAt: timestamp("confirmed_at", { withTimezone: true }).notNull().defaultNow(),
    // --- written by the bank ---
    donatedAt: date("donated_at"),
    bagRfidTag: text("bag_rfid_tag"),
    markedBy: uuid("marked_by").references(() => doctors.id, { onDelete: "set null" }),
    // --- written by the bot once it has processed the bank's mark ---
    botAcknowledgedAt: timestamp("bot_acknowledged_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("donor_demand_confirmations_uq").on(table.demandId, table.telegramUserId),
    index("donor_demand_confirmations_status_idx").on(table.status),
  ]
);

export const bloodBagsRelations = relations(bloodBags, ({ one }) => ({
  issuedToRequest: one(bloodRequests, {
    fields: [bloodBags.issuedToRequestId],
    references: [bloodRequests.id],
  }),
}));

export const bankDecisionsRelations = relations(bankDecisions, ({ one }) => ({
  bloodRequest: one(bloodRequests, {
    fields: [bankDecisions.bloodRequestId],
    references: [bloodRequests.id],
  }),
  decidedByUser: one(doctors, {
    fields: [bankDecisions.decidedBy],
    references: [doctors.id],
  }),
}));

export const donorDemandRelations = relations(donorDemand, ({ one, many }) => ({
  bloodRequest: one(bloodRequests, {
    fields: [donorDemand.bloodRequestId],
    references: [bloodRequests.id],
  }),
  confirmations: many(donorDemandConfirmations),
}));

export const donorDemandConfirmationsRelations = relations(
  donorDemandConfirmations,
  ({ one }) => ({
    demand: one(donorDemand, {
      fields: [donorDemandConfirmations.demandId],
      references: [donorDemand.id],
    }),
  })
);
