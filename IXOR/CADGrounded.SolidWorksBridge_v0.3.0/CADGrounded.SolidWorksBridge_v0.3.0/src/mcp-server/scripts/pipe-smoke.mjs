import { bridgeCall } from "../pipe-client.mjs";

const method = process.argv[2] ?? "sw_status";

let params = {};
if (method === "sw_query_components") {
  params = { top_level_only: true };
}

if (!new Set(["sw_status", "sw_query_components"]).has(method)) {
  console.error("Usage: node scripts/pipe-smoke.mjs sw_status|sw_query_components");
  process.exit(2);
}

try {
  const response = await bridgeCall(method, params);
  console.log(JSON.stringify(response, null, 2));
  process.exit(response?.Ok ? 0 : 1);
} catch (error) {
  console.error(error.stack ?? error.message);
  process.exit(1);
}
