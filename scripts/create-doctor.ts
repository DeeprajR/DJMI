import "dotenv/config";

import { eq } from "drizzle-orm";
import { db } from "../src/db/client";
import { doctors } from "../src/db/schema";
import { hashPassword } from "../src/lib/auth/password";

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
	const email = (getArg("--email") || process.env.DOCTOR_EMAIL || "")
		.trim()
		.toLowerCase();
	const password = getArg("--password") || process.env.DOCTOR_PASSWORD || "";
	const doctorName = (getArg("--name") || process.env.DOCTOR_NAME || "").trim();
	const provisionalReg = (
		getArg("--provisional-reg") || process.env.DOCTOR_PROVISIONAL_REG || ""
	).trim();

	if (!email || !password || !doctorName || !provisionalReg) {
		throw new Error(
			"Provide --email, --password, --name, --provisional-reg or matching DOCTOR_* environment variables."
		);
	}

	const passwordHash = await hashPassword(password);

	const existing = await db.query.doctors.findFirst({
		where: eq(doctors.email, email),
	});

	if (existing) {
		await db
			.update(doctors)
			.set({
				passwordHash,
				role: "doctor",
				doctorName,
				doctorProvisionalReg: provisionalReg,
				isActive: true,
				updatedAt: new Date(),
			})
			.where(eq(doctors.id, existing.id));

		console.log(`Updated doctor account: ${email}`);
		return;
	}

	await db.insert(doctors).values({
		email,
		passwordHash,
		role: "doctor",
		doctorName,
		doctorProvisionalReg: provisionalReg,
		isActive: true,
	});

	console.log(`Created doctor account: ${email}`);
}

main()
	.then(() => process.exit(0))
	.catch((error) => {
		console.error(error);
		process.exit(1);
	});
