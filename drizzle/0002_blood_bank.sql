CREATE TYPE "public"."bag_status" AS ENUM('available', 'reserved', 'issued', 'discarded', 'expired');--> statement-breakpoint
CREATE TYPE "public"."bank_decision" AS ENUM('approved', 'partial', 'declined');--> statement-breakpoint
CREATE TYPE "public"."confirmation_status" AS ENUM('confirmed', 'completed', 'cancelled', 'no_show');--> statement-breakpoint
CREATE TYPE "public"."demand_status" AS ENUM('open', 'fulfilled', 'completed', 'cancelled', 'expired');--> statement-breakpoint
CREATE TYPE "public"."demand_trigger" AS ENUM('request_shortfall', 'stock_floor');--> statement-breakpoint
ALTER TYPE "public"."user_role" ADD VALUE 'blood_bank';--> statement-breakpoint
CREATE TABLE "bank_decisions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"blood_request_id" uuid NOT NULL,
	"decision" "bank_decision" NOT NULL,
	"units_requested" integer NOT NULL,
	"units_issued" integer DEFAULT 0 NOT NULL,
	"note" text,
	"decided_by" uuid,
	"decided_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "bank_decisions_units_non_negative" CHECK ("bank_decisions"."units_issued" >= 0),
	CONSTRAINT "bank_decisions_issued_within_requested" CHECK ("bank_decisions"."units_issued" <= "bank_decisions"."units_requested")
);
--> statement-breakpoint
CREATE TABLE "bank_settings" (
	"id" integer PRIMARY KEY DEFAULT 1 NOT NULL,
	"hospital_name" text NOT NULL,
	"hospital_address" text NOT NULL,
	"district" text NOT NULL,
	"city" text NOT NULL,
	"min_units_per_group" integer DEFAULT 25 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_by" uuid,
	CONSTRAINT "bank_settings_singleton" CHECK ("bank_settings"."id" = 1),
	CONSTRAINT "bank_settings_floor_non_negative" CHECK ("bank_settings"."min_units_per_group" >= 0)
);
--> statement-breakpoint
CREATE TABLE "blood_bags" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"rfid_tag" text NOT NULL,
	"blood_group" "blood_group" NOT NULL,
	"product" "blood_product" DEFAULT 'whole_blood' NOT NULL,
	"collected_at" date NOT NULL,
	"expires_at" date NOT NULL,
	"status" "bag_status" DEFAULT 'available' NOT NULL,
	"issued_to_request_id" uuid,
	"issued_at" timestamp with time zone,
	"added_by" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "blood_bags_expiry_after_collection" CHECK ("blood_bags"."expires_at" >= "blood_bags"."collected_at")
);
--> statement-breakpoint
CREATE TABLE "donor_demand" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"trigger" "demand_trigger" NOT NULL,
	"blood_request_id" uuid,
	"blood_group" "blood_group" NOT NULL,
	"product" "blood_product" DEFAULT 'whole_blood' NOT NULL,
	"units" integer NOT NULL,
	"date_needed" date NOT NULL,
	"hospital_name" text NOT NULL,
	"hospital_address" text NOT NULL,
	"district" text NOT NULL,
	"city" text NOT NULL,
	"notes" text,
	"status" "demand_status" DEFAULT 'open' NOT NULL,
	"bot_public_id" text,
	"bot_imported_at" timestamp with time zone,
	"confirmed_units" integer DEFAULT 0 NOT NULL,
	"waitlisted_units" integer DEFAULT 0 NOT NULL,
	"completed_units" integer DEFAULT 0 NOT NULL,
	"notified_donors" integer DEFAULT 0 NOT NULL,
	"created_by" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"closed_at" timestamp with time zone,
	CONSTRAINT "donor_demand_units_positive" CHECK ("donor_demand"."units" > 0)
);
--> statement-breakpoint
CREATE TABLE "donor_demand_confirmations" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"demand_id" uuid NOT NULL,
	"telegram_user_id" bigint NOT NULL,
	"donor_name" text,
	"donor_phone" text,
	"blood_group" "blood_group",
	"status" "confirmation_status" DEFAULT 'confirmed' NOT NULL,
	"confirmed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"donated_at" date,
	"bag_rfid_tag" text,
	"marked_by" uuid,
	"bot_acknowledged_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "bank_decisions" ADD CONSTRAINT "bank_decisions_blood_request_id_blood_requests_id_fk" FOREIGN KEY ("blood_request_id") REFERENCES "public"."blood_requests"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "bank_decisions" ADD CONSTRAINT "bank_decisions_decided_by_doctors_id_fk" FOREIGN KEY ("decided_by") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "bank_settings" ADD CONSTRAINT "bank_settings_updated_by_doctors_id_fk" FOREIGN KEY ("updated_by") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_bags" ADD CONSTRAINT "blood_bags_issued_to_request_id_blood_requests_id_fk" FOREIGN KEY ("issued_to_request_id") REFERENCES "public"."blood_requests"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_bags" ADD CONSTRAINT "blood_bags_added_by_doctors_id_fk" FOREIGN KEY ("added_by") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "donor_demand" ADD CONSTRAINT "donor_demand_blood_request_id_blood_requests_id_fk" FOREIGN KEY ("blood_request_id") REFERENCES "public"."blood_requests"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "donor_demand" ADD CONSTRAINT "donor_demand_created_by_doctors_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "donor_demand_confirmations" ADD CONSTRAINT "donor_demand_confirmations_demand_id_donor_demand_id_fk" FOREIGN KEY ("demand_id") REFERENCES "public"."donor_demand"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "donor_demand_confirmations" ADD CONSTRAINT "donor_demand_confirmations_marked_by_doctors_id_fk" FOREIGN KEY ("marked_by") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "bank_decisions_request_uq" ON "bank_decisions" USING btree ("blood_request_id");--> statement-breakpoint
CREATE UNIQUE INDEX "blood_bags_rfid_tag_uq" ON "blood_bags" USING btree ("rfid_tag");--> statement-breakpoint
CREATE INDEX "blood_bags_group_status_idx" ON "blood_bags" USING btree ("blood_group","status");--> statement-breakpoint
CREATE INDEX "blood_bags_expires_at_idx" ON "blood_bags" USING btree ("expires_at");--> statement-breakpoint
CREATE UNIQUE INDEX "donor_demand_bot_public_id_uq" ON "donor_demand" USING btree ("bot_public_id") WHERE "donor_demand"."bot_public_id" IS NOT NULL;--> statement-breakpoint
CREATE INDEX "donor_demand_status_idx" ON "donor_demand" USING btree ("status");--> statement-breakpoint
CREATE INDEX "donor_demand_request_idx" ON "donor_demand" USING btree ("blood_request_id");--> statement-breakpoint
CREATE UNIQUE INDEX "donor_demand_confirmations_uq" ON "donor_demand_confirmations" USING btree ("demand_id","telegram_user_id");--> statement-breakpoint
CREATE INDEX "donor_demand_confirmations_status_idx" ON "donor_demand_confirmations" USING btree ("status");