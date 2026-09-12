import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bridgeCall } from "../pipe-client.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const expectedPath = path.resolve(here, "../../../docs/CURRENT_BENCHMARK_EXPECTED.json");
const expected = JSON.parse(await fs.readFile(expectedPath, "utf8"));

const status = await bridgeCall("sw_status", {});
if (!status?.Ok) throw new Error(`sw_status failed: ${JSON.stringify(status?.Error)}`);
const title = status.Result?.active_document?.title ?? "";
if (!title.includes(expected.document_title_contains)) {
  throw new Error(`Active document title mismatch: '${title}' does not contain '${expected.document_title_contains}'.`);
}

const query = await bridgeCall("sw_query_components", { top_level_only: true });
if (!query?.Ok) throw new Error(`sw_query_components failed: ${JSON.stringify(query?.Error)}`);
const actualComponents = new Map((query.Result?.components ?? []).map(c => [c.name2, c]));

const absArray = (actual, want, tol, label) => {
  if (!Array.isArray(actual) || actual.length !== want.length) {
    throw new Error(`${label}: array shape mismatch.`);
  }
  for (let i = 0; i < want.length; i++) {
    const d = Math.abs(actual[i] - want[i]);
    if (d > tol) throw new Error(`${label}[${i}] delta=${d} exceeds tolerance ${tol}; actual=${actual[i]} expected=${want[i]}`);
  }
};

for (const want of expected.components) {
  const actual = actualComponents.get(want.name2);
  if (!actual) throw new Error(`Missing top-level component: ${want.name2}`);
  if (actual.fixed !== want.fixed) throw new Error(`${want.name2}: fixed=${actual.fixed}, expected=${want.fixed}`);
  absArray(actual.rotation9, want.rotation9, expected.tolerances.rotation_abs, `${want.name2}.rotation9`);
  absArray(actual.translation_mm, want.translation_mm, expected.tolerances.translation_mm_abs, `${want.name2}.translation_mm`);

  const box = actual.bounding_box_mm_approx;
  if (!box) throw new Error(`${want.name2}: no GetBox result.`);
  absArray(box.min, want.bounding_box_mm_approx.min, expected.tolerances.getbox_mm_abs, `${want.name2}.bbox.min`);
  absArray(box.max, want.bounding_box_mm_approx.max, expected.tolerances.getbox_mm_abs, `${want.name2}.bbox.max`);
}

console.log("PASS: current SOLIDWORKS benchmark matches CADGrounded v0.1 canonical expectations.");
console.log(`Document: ${title}`);
console.log(`Verified components: ${expected.components.map(c => c.name2).join(", ")}`);
console.log("Note: GetBox comparisons are approximate sanity checks, not precision geometry validation.");
