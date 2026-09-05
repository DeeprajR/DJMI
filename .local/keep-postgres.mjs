import path from "node:path";
import { fileURLToPath } from "node:url";
import EmbeddedPostgres from "embedded-postgres";

process.env.LANG = "C";
process.env.LC_ALL = "C";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pg = new EmbeddedPostgres({
  databaseDir: path.join(repoRoot, ".local", "embedded-postgres"),
  user: "postgres",
  password: "postgres",
  port: 55432,
  persistent: true,
  initdbFlags: ["--locale=C", "--encoding=UTF8"],
});

await pg.initialise();
await pg.start();
try {
  await pg.createDatabase("blood_request");
} catch {
  // already exists
}
console.log("LOCAL_POSTGRES_READY postgresql://postgres:postgres@127.0.0.1:55432/blood_request");
await new Promise(() => {});
