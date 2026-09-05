/** Synthetic local-only fixtures. Never connect this preview to clinical data. */
import { spawn } from "node:child_process";
import path from "node:path";
import EmbeddedPostgres from "embedded-postgres";
import { Pool } from "pg";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import { createHash } from "node:crypto";

const secret = "local-design-preview-only-not-a-production-secret";
const token = "synthetic-design-preview-session";
const doctorId = "11111111-1111-4111-8111-111111111111";
const patientId = "22222222-2222-4222-8222-222222222222";
const draftId = "33333333-3333-4333-8333-333333333333";
const submittedId = "44444444-4444-4444-8444-444444444444";
const databaseUrl = "postgresql://postgres:preview@127.0.0.1:55433/design_preview";
process.env.LANG = "C";
process.env.LC_ALL = "C";

const postgres = new EmbeddedPostgres({
  databaseDir: path.join(process.cwd(), ".local", "design-preview"),
  user: "postgres", password: "preview", port: 55433, persistent: false,
  initdbFlags: ["--locale=C", "--encoding=UTF8"],
});

async function main() {
  await postgres.initialise();
  await postgres.start();
  await postgres.createDatabase("design_preview");
  const pool = new Pool({ connectionString: databaseUrl });
  try {
    await migrate(drizzle(pool), { migrationsFolder: "drizzle" });
    await pool.query(`INSERT INTO doctors (id, email, password_hash, doctor_name, doctor_provisional_reg)
      VALUES ($1, 'preview@example.invalid', 'login-disabled', 'Dr. Preview Only', 'TEST-001')`, [doctorId]);
    await pool.query(`INSERT INTO patients (id, patient_name, patient_age, patient_blood_group)
      VALUES ($1, 'Synthetic patient — not a real person', 32, 'O+')`, [patientId]);
    await pool.query(`INSERT INTO admissions (ip_no, patient_id, ward_no)
      VALUES ('PREVIEW-001', $1, 'Ward 04')`, [patientId]);
    for (const [id, submitted] of [[draftId, false], [submittedId, true]] as const) {
      await pool.query(`INSERT INTO blood_requests (id, ip_no, doctor_id, reason_for_transfusion,
        date_needed, requested_blood_group, product, units, status, request_id, submitted_at)
        VALUES ($1, 'PREVIEW-001', $2, 'Synthetic request for interface testing only',
        '2026-09-10', 'O+', 'packed_rbc', 2, $3, $4, $5)`,
      [id, doctorId, submitted ? "submitted" : "draft", submitted ? "BR-2026-000001" : null, submitted ? new Date() : null]);
    }
    await pool.query(`INSERT INTO blood_samples (blood_request_id, sample_identifier, collected_at, collected_by_doctor_id)
      VALUES ($1, 'PREVIEW-SAMPLE-001', now(), $2)`, [submittedId, doctorId]);
    await pool.query(`INSERT INTO blood_request_counters (request_year, current_value) VALUES (2026, 1)`);
    await pool.query(`INSERT INTO sessions (doctor_id, token_hash, expires_at) VALUES ($1, $2, now() + interval '2 hours')`,
      [doctorId, createHash("sha256").update(`${token}:${secret}`).digest("hex")]);
  } finally {
    await pool.end();
  }
  const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3100"], {
    stdio: "inherit",
    env: { ...process.env, DATABASE_URL: databaseUrl, SESSION_SECRET: secret },
  });
  let stopping = false;
  async function stop() {
    if (stopping) return;
    stopping = true;
    server.kill("SIGTERM");
    await postgres.stop();
  }
  process.once("SIGINT", () => void stop());
  process.once("SIGTERM", () => void stop());
  server.once("exit", () => void stop());
  server.once("error", () => void stop());
  console.log("Synthetic preview: http://127.0.0.1:3100. Test cookie br_session=synthetic-design-preview-session");
}

main().catch(async (error) => {
  console.error(error);
  await postgres.stop();
  process.exitCode = 1;
});