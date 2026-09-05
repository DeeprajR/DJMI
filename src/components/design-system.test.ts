import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const css = readFileSync(path.join(process.cwd(), "src/app/design-system.css"), "utf8");
function luminance(hex: string) {
  const channels = hex.replace("#", "").match(/../g)!.map((channel) => {
    const value = parseInt(channel, 16) / 255;
    return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
  });
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}
function token(name: string) {
  const value = css.match(new RegExp(`--${name}: (#[a-f0-9]{6})`, "i"))?.[1];
  assert.ok(value, `Missing token ${name}`);
  return value;
}

test("design-system text and semantic notices meet WCAG AA normal-text contrast", () => {
  const pairs = [
    [token("neutral-900"), token("neutral-0")],
    [token("neutral-500"), token("neutral-25")],
    [token("neutral-0"), token("crimson-600")],
    [token("crimson-900"), token("crimson-100")],
    [token("green-800"), token("green-100")],
    [token("amber-800"), token("amber-100")],
    [token("blue-800"), token("blue-100")],
    ["#edf0f4", "#181d24"], ["#9aa3b0", "#181d24"],
  ];
  for (const [fg, bg] of pairs) {
    const light = luminance(fg), dark = luminance(bg);
    const ratio = (Math.max(light, dark) + .05) / (Math.min(light, dark) + .05);
    assert.ok(ratio >= 4.5, `${fg} on ${bg}: ${ratio.toFixed(2)}`);
  }
});

test("shared controls and navigation retain touch, safe-area and reduced-motion rules", () => {
  assert.match(css, /\.button \{[^}]*min-width: 48px; min-height: 48px;/);
  assert.match(css, /\.input \{[^}]*min-height: 52px;/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /\.form-stack \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
});

test("all application pages expose a focusable main landmark and avoid old visual styles", () => {
  const root = path.join(process.cwd(), "src/app");
  function walk(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => entry.isDirectory()
      ? walk(path.join(dir, entry.name))
      : entry.name === "page.tsx" ? [path.join(dir, entry.name)] : []);
  }
  for (const file of walk(root)) {
    const source = readFileSync(file, "utf8");
    assert.match(source, /id="main-content" tabIndex=\{-1\}/, file);
    assert.doesNotMatch(source, /(?:bg|text|border)-slate-|text-\[11px\]/, file);
  }
});

test("draft and review screens retain frozen form wording", () => {
  const labels = ["Name of Patient:", "Age of Patient:", "Blood Group of Patient:", "IP No. of Patient:", "Ward No.:", "Reason for transfusion:", "Date Needed:", "Blood Group:", "No. of Units:", "Doctor name:", "Doctor Provisional Reg.:", "Doctor Seal:", "Request: Whole Blood, Packed RBC, Platelet, Fresh Frozen Plasma, Cryopresipitate"];
  for (const route of ["new", "[id]", "[id]/review", "[id]/view"]) {
    const source = readFileSync(path.join(process.cwd(), "src/app/requests", route, "page.tsx"), "utf8");
    for (const label of labels) assert.ok(source.includes(label), `${route} missing ${label}`);
  }
});