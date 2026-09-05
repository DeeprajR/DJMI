CREATE TYPE "public"."admission_status" AS ENUM('active', 'discharged');--> statement-breakpoint
CREATE TYPE "public"."age_unit" AS ENUM('days', 'months', 'years');--> statement-breakpoint
CREATE TYPE "public"."audit_actor_type" AS ENUM('doctor', 'admin', 'system');--> statement-breakpoint
CREATE TYPE "public"."blood_group" AS ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-');--> statement-breakpoint
CREATE TYPE "public"."blood_product" AS ENUM('whole_blood', 'packed_rbc', 'platelet', 'fresh_frozen_plasma', 'cryopresipitate');--> statement-breakpoint
CREATE TYPE "public"."request_status" AS ENUM('draft', 'submitted', 'cancelled');--> statement-breakpoint
CREATE TYPE "public"."user_role" AS ENUM('doctor', 'admin');--> statement-breakpoint
CREATE TABLE "admissions" (
	"ip_no" text PRIMARY KEY NOT NULL,
	"patient_id" uuid NOT NULL,
	"ward_no" text NOT NULL,
	"admitted_at" timestamp with time zone DEFAULT now() NOT NULL,
	"discharged_at" timestamp with time zone,
	"admission_status" "admission_status" DEFAULT 'active' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "audit_log" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"actor_type" "audit_actor_type" NOT NULL,
	"actor_doctor_id" uuid,
	"action" text NOT NULL,
	"entity_type" text NOT NULL,
	"entity_id" text NOT NULL,
	"metadata" text,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "blood_request_counters" (
	"request_year" integer PRIMARY KEY NOT NULL,
	"current_value" bigint DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "blood_request_counters_non_negative" CHECK ("blood_request_counters"."current_value" >= 0)
);
--> statement-breakpoint
CREATE TABLE "blood_requests" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"request_id" text,
	"ip_no" text NOT NULL,
	"patient_name_snapshot" text,
	"patient_age_snapshot" integer,
	"patient_age_unit_snapshot" "age_unit",
	"patient_blood_group_snapshot" "blood_group",
	"ward_no_snapshot" text,
	"reason_for_transfusion" text,
	"date_needed" date,
	"requested_blood_group" "blood_group",
	"product" "blood_product",
	"units" integer,
	"doctor_id" uuid NOT NULL,
	"doctor_name_snapshot" text,
	"doctor_provisional_reg_snapshot" text,
	"doctor_seal_path_snapshot" text,
	"status" "request_status" DEFAULT 'draft' NOT NULL,
	"submitted_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "blood_requests_units_positive" CHECK ("blood_requests"."units" IS NULL OR "blood_requests"."units" > 0),
	CONSTRAINT "blood_requests_submitted_consistency" CHECK (("blood_requests"."status" <> 'submitted'::request_status) OR ("blood_requests"."request_id" IS NOT NULL AND "blood_requests"."submitted_at" IS NOT NULL))
);
--> statement-breakpoint
CREATE TABLE "blood_samples" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"blood_request_id" uuid NOT NULL,
	"sample_identifier" text NOT NULL,
	"collected_at" timestamp with time zone NOT NULL,
	"collected_by_doctor_id" uuid NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "doctors" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" varchar(320) NOT NULL,
	"password_hash" text NOT NULL,
	"role" "user_role" DEFAULT 'doctor' NOT NULL,
	"doctor_name" text NOT NULL,
	"doctor_provisional_reg" text NOT NULL,
	"doctor_seal_path" text,
	"is_active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "patients" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"patient_name" text NOT NULL,
	"patient_age" integer NOT NULL,
	"patient_age_unit" "age_unit" DEFAULT 'years' NOT NULL,
	"patient_blood_group" "blood_group" NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "patients_age_non_negative" CHECK ("patients"."patient_age" >= 0)
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"doctor_id" uuid NOT NULL,
	"token_hash" text NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"revoked_at" timestamp with time zone
);
--> statement-breakpoint
ALTER TABLE "admissions" ADD CONSTRAINT "admissions_patient_id_patients_id_fk" FOREIGN KEY ("patient_id") REFERENCES "public"."patients"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_actor_doctor_id_doctors_id_fk" FOREIGN KEY ("actor_doctor_id") REFERENCES "public"."doctors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_requests" ADD CONSTRAINT "blood_requests_ip_no_admissions_ip_no_fk" FOREIGN KEY ("ip_no") REFERENCES "public"."admissions"("ip_no") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_requests" ADD CONSTRAINT "blood_requests_doctor_id_doctors_id_fk" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_samples" ADD CONSTRAINT "blood_samples_blood_request_id_blood_requests_id_fk" FOREIGN KEY ("blood_request_id") REFERENCES "public"."blood_requests"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "blood_samples" ADD CONSTRAINT "blood_samples_collected_by_doctor_id_doctors_id_fk" FOREIGN KEY ("collected_by_doctor_id") REFERENCES "public"."doctors"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_doctor_id_doctors_id_fk" FOREIGN KEY ("doctor_id") REFERENCES "public"."doctors"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "admissions_patient_id_idx" ON "admissions" USING btree ("patient_id");--> statement-breakpoint
CREATE INDEX "admissions_status_idx" ON "admissions" USING btree ("admission_status");--> statement-breakpoint
CREATE INDEX "audit_log_occurred_at_idx" ON "audit_log" USING btree ("occurred_at");--> statement-breakpoint
CREATE INDEX "audit_log_entity_idx" ON "audit_log" USING btree ("entity_type","entity_id");--> statement-breakpoint
CREATE UNIQUE INDEX "blood_requests_request_id_uq" ON "blood_requests" USING btree ("request_id") WHERE "blood_requests"."request_id" IS NOT NULL;--> statement-breakpoint
CREATE INDEX "blood_requests_ip_no_idx" ON "blood_requests" USING btree ("ip_no");--> statement-breakpoint
CREATE INDEX "blood_requests_doctor_id_idx" ON "blood_requests" USING btree ("doctor_id");--> statement-breakpoint
CREATE INDEX "blood_requests_status_idx" ON "blood_requests" USING btree ("status");--> statement-breakpoint
CREATE UNIQUE INDEX "blood_samples_identifier_uq" ON "blood_samples" USING btree ("sample_identifier");--> statement-breakpoint
CREATE INDEX "blood_samples_request_id_idx" ON "blood_samples" USING btree ("blood_request_id");--> statement-breakpoint
CREATE UNIQUE INDEX "doctors_email_uq" ON "doctors" USING btree ("email");--> statement-breakpoint
CREATE UNIQUE INDEX "doctors_provisional_reg_uq" ON "doctors" USING btree ("doctor_provisional_reg");--> statement-breakpoint
CREATE INDEX "patients_name_idx" ON "patients" USING btree ("patient_name");--> statement-breakpoint
CREATE UNIQUE INDEX "sessions_token_hash_uq" ON "sessions" USING btree ("token_hash");--> statement-breakpoint
CREATE INDEX "sessions_doctor_id_idx" ON "sessions" USING btree ("doctor_id");--> statement-breakpoint
CREATE INDEX "sessions_expires_at_idx" ON "sessions" USING btree ("expires_at");