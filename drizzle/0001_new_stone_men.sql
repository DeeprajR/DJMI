CREATE TABLE "auth_rate_limits" (
	"scope" text NOT NULL,
	"key" text NOT NULL,
	"attempts" integer DEFAULT 0 NOT NULL,
	"window_started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"blocked_until" timestamp with time zone,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "auth_rate_limits_pk" PRIMARY KEY("scope","key"),
	CONSTRAINT "auth_rate_limits_scope_check" CHECK ("auth_rate_limits"."scope" IN ('login_ip', 'login_account')),
	CONSTRAINT "auth_rate_limits_attempts_non_negative" CHECK ("auth_rate_limits"."attempts" >= 0)
);
--> statement-breakpoint
CREATE INDEX "auth_rate_limits_blocked_until_idx" ON "auth_rate_limits" USING btree ("blocked_until");