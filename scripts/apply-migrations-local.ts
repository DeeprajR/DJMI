import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import EmbeddedPostgres from "embedded-postgres";
import { Client } from "pg";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const port = 55432;
const user = "postgres";
const password = "postgres";
const database = "blood_request";

process.env.LANG = "C";
process.env.LC_ALL = "C";

const pg = new EmbeddedPostgres({
  databaseDir: path.join(repoRoot, ".local", "embedded-postgres"),
  user,
  password,
  port,
  persistent: true,
  initdbFlags: ["--locale=C", "--encoding=UTF8"],
});

function runDrizzleMigrate(databaseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn("npm", ["run", "db:migrate"], {
      cwd: repoRoot,
      stdio: "inherit",
      env: {
        ...process.env,
        DATABASE_URL: databaseUrl,
      },
    });

    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`db:migrate failed with exit code ${code ?? "unknown"}`));
    });
  });
}

async function verifyMigrations(databaseUrl: string): Promise<void> {
  const client = new Client({ connectionString: databaseUrl });
  await client.connect();

  try {
    const result = await client.query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    );

    console.log("Applied schema tables:");
    for (const row of result.rows) {
      console.log(`- ${row.table_name}`);
    }
  } finally {
    await client.end();
  }
}

async function main() {
  const databaseUrl = `postgresql://${user}:${password}@127.0.0.1:${port}/${database}`;

  await pg.initialise();
  await pg.start();

  try {
    await pg.createDatabase(database);
  } catch {
    // Database already exists from previous run.
  }

  try {
    await runDrizzleMigrate(databaseUrl);
    await verifyMigrations(databaseUrl);
    console.log("Local migration apply completed successfully.");
  } finally {
    await pg.stop();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
