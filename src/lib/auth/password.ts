import "server-only";

import { hash, verify } from "@node-rs/argon2";

const ARGON2_MEMORY_COST = 19_456;
const ARGON2_TIME_COST = 2;
const ARGON2_PARALLELISM = 1;

export async function hashPassword(password: string): Promise<string> {
  return hash(password, {
    algorithm: 2,
    memoryCost: ARGON2_MEMORY_COST,
    timeCost: ARGON2_TIME_COST,
    parallelism: ARGON2_PARALLELISM,
  });
}

export async function verifyPassword(
  password: string,
  hashedPassword: string
): Promise<boolean> {
  return verify(hashedPassword, password);
}
