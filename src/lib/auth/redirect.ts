export function sanitizeNextPath(nextPath: string | undefined): string {
  if (!nextPath) {
    return "/dashboard";
  }
  if (!nextPath.startsWith("/")) {
    return "/dashboard";
  }
  if (nextPath.startsWith("//") || nextPath.startsWith("/\\")) {
    return "/dashboard";
  }
  return nextPath;
}
