import "dotenv/config";

import { eq } from "drizzle-orm";
import { db } from "../src/db/client";
import { doctors } from "../src/db/schema";
import { hashPassword } from "../src/lib/auth/password";

/**
 * Provision a blood-bank staff account (role `blood_bank`).
 *
 *   npm run seed:bank -- --email bank@example.com --password change-me-please --name "Blood Bank Counter"
 *
 * Accounts live in the `doctors` table because that is where sessions point; the
 * provisional-registration field is filled with a BANK-* marker since bank staff have
 * no medical registration. Re-running updates the password and re-activates the account.
 */
function getArg(flag: string): string | undefined {
	const idx = process.argv.indexOf(flag);
	if (idx === -1) {
		return undefined;
	}
	const value = process.argv[idx + 1];
	if (!value || value.startsWith("--")) {
		return undefined;
	}
	return value;
}

async function main() {
	const email = (getArg("--email") || process.env.BANK_EMAIL || "").trim().toLowerCase();
	const password = getArg("--password") || process.env.BANK_PASSWORD || "";
	const name = (getArg("--name") || process.env.BANK_NAME || "Blood Bank").trim();

	if (!email || !password) {
		throw new Error("Provide --email and --password (12+ characters), or BANK_EMAIL / BANK_PASSWORD.");
	}
	if (password.length < 12) {
		throw new Error("Password must be at least 12 characters.");
	}

	const passwordHash = await hashPassword(password);
	const marker = `BANK-${email.replace(/[^a-z0-9]/gi, "").slice(0, 20).toUpperCase()}`;

	const existing = await db.query.doctors.findFirst({ where: eq(doctors.email, email) });

	if (existing) {
		await db
			.update(doctors)
			.set({
				passwordHash,
				role: "blood_bank",
				doctorName: name,
				isActive: true,
				updatedAt: new Date(),
			})
			.where(eq(doctors.id, existing.id));
		console.log(`Updated blood bank account: ${email}`);
		return;
	}

	await db.insert(doctors).values({
		email,
		passwordHash,
		role: "blood_bank",
		doctorName: name,
		doctorProvisionalReg: marker,
		isActive: true,
	});
	console.log(`Created blood bank account: ${email} (sign in, then open /bank)`);
}

main()
	.then(() => process.exit(0))
	.catch((error) => {
		console.error(error);
		process.exit(1);
	});
