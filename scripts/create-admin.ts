import "dotenv/config";

import { eq } from "drizzle-orm";
import { db } from "../src/db/client";
import { doctors } from "../src/db/schema";
import { hashPassword } from "../src/lib/auth/password";

async function main() {
	const email = process.env.ADMIN_EMAIL?.trim().toLowerCase();
	const password = process.env.ADMIN_PASSWORD;
	const doctorName = process.env.ADMIN_NAME?.trim();
	const provisionalReg = process.env.ADMIN_PROVISIONAL_REG?.trim();

	if (!email || !password || !doctorName || !provisionalReg) {
		throw new Error(
			"Missing ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME, or ADMIN_PROVISIONAL_REG in environment."
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
				role: "admin",
				doctorName,
				doctorProvisionalReg: provisionalReg,
				isActive: true,
				updatedAt: new Date(),
			})
			.where(eq(doctors.id, existing.id));

		console.log(`Updated admin account: ${email}`);
		return;
	}

	await db.insert(doctors).values({
		email,
		passwordHash,
		role: "admin",
		doctorName,
		doctorProvisionalReg: provisionalReg,
		isActive: true,
	});

	console.log(`Created admin account: ${email}`);
}

main()
	.then(() => process.exit(0))
	.catch((error) => {
		console.error(error);
		process.exit(1);
	});
