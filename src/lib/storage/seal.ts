import "server-only";

import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import sharp from "sharp";

const MAX_SEAL_BYTES = 1024 * 1024;
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function resolveSealStorageDir(): string {
  const storageDir = process.env.SEAL_STORAGE_DIR;
  if (!storageDir) {
    throw new Error("SEAL_STORAGE_DIR is not configured.");
  }
  return path.resolve(storageDir);
}

function assertPngSignature(buffer: Buffer): void {
  if (buffer.length < PNG_SIGNATURE.length) {
    throw new Error("Invalid PNG file.");
  }
  if (!buffer.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    throw new Error("Invalid PNG file.");
  }
}

function safeFileName(fileName: string): string {
  if (!/^[a-zA-Z0-9._-]+\.png$/.test(fileName)) {
    throw new Error("Invalid seal file name.");
  }
  return fileName;
}

export async function storeSealImage(
  fileBuffer: Buffer,
  doctorId: string,
  existingFileName?: string | null
): Promise<string> {
  if (fileBuffer.byteLength > MAX_SEAL_BYTES) {
    throw new Error("Seal PNG must be 1MB or smaller.");
  }

  assertPngSignature(fileBuffer);

  const normalized = await sharp(fileBuffer)
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer();

  const dir = resolveSealStorageDir();
  await fs.mkdir(dir, { recursive: true });

  const newFileName = `${doctorId}-${randomUUID()}.png`;
  const absolutePath = path.join(dir, newFileName);
  await fs.writeFile(absolutePath, normalized, { mode: 0o600 });

  if (existingFileName) {
    const oldPath = path.join(dir, safeFileName(existingFileName));
    await fs.rm(oldPath, { force: true });
  }

  return newFileName;
}

export async function readSealImage(fileName: string): Promise<Buffer> {
  const dir = resolveSealStorageDir();
  const absolutePath = path.join(dir, safeFileName(fileName));
  return fs.readFile(absolutePath);
}
