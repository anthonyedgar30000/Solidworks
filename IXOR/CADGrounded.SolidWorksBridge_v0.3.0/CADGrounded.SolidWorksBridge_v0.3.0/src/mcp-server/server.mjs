import { createServer } from "node:http";
import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import { toNodeHandler } from "@modelcontextprotocol/node";
import * as z from "zod/v4";
import { executeCode } from "./execution-handler.mjs";
import { bridgeCall } from "./pipe-client.mjs";
import { insertComponent } from "./insertion-handler.mjs";

const HOST = process.env.SWBRIDGE_HOST ?? "127.0.0.1";
const PORT = Number(process.env.SWBRIDGE_PORT ?? "8765");
const MAX_CONTROL = process.env.SWBRIDGE_MAX_CONTROL === "1";
const ALLOW_WRITES = process.env.SWBRIDGE_ALLOW_WRITES === "1";

const rotationSchema = z.array(z.number().finite()).length(9);
const translationSchema = z.array(z.number().finite()).length(3);

function validateRotation9(r, tol = 1e-8) {
  const row = (i) => [r[i * 3], r[i * 3 + 1], r[i * 3 + 2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const norm = (a) => Math.sqrt(dot(a, a));

  const a = row(0), b = row(1), c = row(2);
  if (Math.abs(norm(a) - 1) > tol || Math.abs(norm(b) - 1) > tol || Math.abs(norm(c) - 1) > tol) {
    throw new Error("rotation9 rows are not unit length.");
  }
  if (Math.abs(dot(a, b)) > tol || Math.abs(dot(a, c)) > tol || Math.abs(dot(b, c)) > tol) {
    throw new Error("rotation9 rows are not orthogonal.");
  }

  const det =
    r[0] * (r[4] * r[8] - r[5] * r[7]) -
    r[1] * (r[3] * r[8] - r[5] * r[6]) +
    r[2] * (r[3] * r[7] - r[4] * r[6]);

  if (Math.abs(det - 1) > tol) {
    throw new Error(`rotation9 must be right-handed with determinant +1; got ${det}.`);
  }
}

function asToolResult(response) {
  if (!response?.Ok) {
    const err = response?.Error ?? { Code: "UNKNOWN_BRIDGE_ERROR", Message: "Unknown bridge failure." };
    return {
      isError: true,
      content: [{ type: "text", text: `${err.Code}: ${err.Message}` }],
      structuredContent: { ok: false, error: { code: err.Code, message: err.Message } },
    };
  }

  const structuredContent = { ok: true, result: response.Result };
  return {
    content: [{ type: "text", text: JSON.stringify(structuredContent, null, 2) }],
    structuredContent,
  };
}

function buildServer() {
  const server = new McpServer(
    { name: "cadgrounded-solidworks-bridge", version: "0.3.0" },
    {
      capabilities: { tools: {} },
      instructions:
        "SOLIDWORKS is the geometry authority. Read actual state before proposing writes. " +
        "Do not infer mechanical correctness from a successful API operation. " +
        "Use sw_set_transform with apply=false first; actual writes require the local write gate and a floating component.",
    },
  );

  server.registerTool(
    "sw_status",
    {
      title: "SOLIDWORKS Status",
      description: "Use this when you need the active SOLIDWORKS document/session status from the live desktop application.",
      inputSchema: z.object({}),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async () => asToolResult(await bridgeCall("sw_status", {})),
  );

  server.registerTool(
    "sw_query_components",
    {
      title: "Query SOLIDWORKS Components",
      description:
        "Use this when you need live component identity, source path, fixed/suppressed state, Transform2, and approximate GetBox envelopes from the active SOLIDWORKS assembly.",
      inputSchema: z.object({
        top_level_only: z.boolean().default(true).describe("True returns top-level assembly components only."),
      }),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ top_level_only }) => asToolResult(
      await bridgeCall("sw_query_components", { top_level_only }),
    ),
  );

  server.registerTool(
    "sw_set_transform",
    {
      title: "Set Exact SOLIDWORKS Component Transform",
      description:
        "Use this only after reading the live assembly state and establishing the deterministic target transform. " +
        "The exact top-level component must be floating. apply=false is a dry run. apply=true is a write and is rejected unless the local write gate is enabled.",
      inputSchema: z.object({
        component_name: z.string().min(1).describe("Exact top-level Component2.Name2 value."),
        expected_document_title: z.string().min(1).optional().describe("For apply=true, exact active document title from a prior sw_status read."),
        rotation9: rotationSchema.describe("Exact nine values for SOLIDWORKS MathTransform.ArrayData indices 0..8."),
        translation_mm: translationSchema.describe("Exact X,Y,Z translation in millimetres."),
        apply: z.boolean().default(false).describe("False = proposal only. True = perform the write if locally enabled."),
        expected_before: z.object({
          rotation9: rotationSchema.optional(),
          translation_mm: translationSchema.optional(),
          translation_tolerance_mm: z.number().positive().max(10).default(0.001),
        }).optional().describe("Optional compare-and-set guard against stale component state."),
      }),
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ component_name, expected_document_title, rotation9, translation_mm, apply, expected_before }) => {
      try {
        validateRotation9(rotation9);
      } catch (error) {
        return {
          isError: true,
          content: [{ type: "text", text: `INVALID_ROTATION: ${error.message}` }],
          structuredContent: { ok: false, error: { code: "INVALID_ROTATION", message: error.message } },
        };
      }

      if (apply && (!expected_document_title || !expected_before?.rotation9 || !expected_before?.translation_mm)) {
        return {
          isError: true,
          content: [{
            type: "text",
            text: "COMPARE_AND_SET_REQUIRED: apply=true requires expected_document_title plus expected_before.rotation9 and expected_before.translation_mm from prior live reads.",
          }],
          structuredContent: {
            ok: false,
            error: {
              code: "COMPARE_AND_SET_REQUIRED",
              message: "A live document identity and complete before transform are required for writes.",
            },
          },
        };
      }

      if (apply && !ALLOW_WRITES) {
        return {
          isError: true,
          content: [{
            type: "text",
            text: "WRITES_DISABLED: Start the local MCP server with SWBRIDGE_ALLOW_WRITES=1 only for an explicitly controlled write test.",
          }],
          structuredContent: {
            ok: false,
            error: {
              code: "WRITES_DISABLED",
              message: "Local MCP server write gate is disabled.",
            },
          },
        };
      }

      return asToolResult(await bridgeCall("sw_set_transform", {
        component_name,
        ...(expected_document_title ? { expected_document_title } : {}),
        rotation9,
        translation_mm,
        apply,
        ...(expected_before ? { expected_before } : {}),
      }));
    },
  );

  server.registerTool("sw_insert_component", {
    title: "Insert Native SOLIDWORKS Component",
    description: "Insert one saved native SLDPRT/SLDASM at an exact transform. First call apply=false; then use its preflight_token with apply=true. Requires the local write gate. Each additional instance needs a fresh preflight and current source count. Does not import STEP, run macros, create mates or save. On timeout/partial failure query before retrying.",
    inputSchema: z.object({
      source_path: z.string().min(4).describe("Absolute Windows path to a saved native part or assembly."),
      configuration: z.string().min(1).default("Default"),
      expected_document_title: z.string().min(1),
      expected_document_path: z.string().min(1),
      expected_source_instances: z.number().int().min(0).max(100000).describe("Current top-level count using this exact source path, including suppressed instances."),
      rotation9: rotationSchema,
      translation_mm: translationSchema,
      apply: z.boolean().default(false),
      preflight_token: z.string().regex(/^[a-f0-9]{64}$/).optional(),
    }),
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  }, async (params) => {
    try { validateRotation9(params.rotation9); }
    catch (error) { return asToolResult({ Ok: false, Error: { Code: "INVALID_ROTATION", Message: error.message } }); }
    return asToolResult(await insertComponent(params, { allowWrites: ALLOW_WRITES, call: bridgeCall }));
  });

  server.registerTool("sw_execute_code", {
    title: "Execute SOLIDWORKS C# API Code",
    description: "Maximum-control mode: compile then execute trusted C# in the SOLIDWORKS process on its UI thread. Broad API access including documents, features, mates, saves/exports and RunMacro2. Requires local MaxControl mode. Submit complete public static object BridgeScript.Run(SldWorks app). apply=false compiles only; apply=true consumes the returned token with identical source and document. Return plain JSON values. Code can access the Windows account's files/processes; it is not sandboxed. Timeout does not cancel execution. No automatic retry or rollback. Inspect live state after execution.",
    inputSchema: z.object({
      source: z.string().min(1).max(200000),
      expected_document_title: z.string().describe("Exact sw_status title, or empty only if no active document."),
      expected_document_path: z.string().describe("Exact sw_status path, or empty if unsaved/no document."),
      apply: z.boolean().default(false),
      preflight_token: z.string().regex(/^[a-f0-9]{32}$/).optional(),
    }),
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
  }, async (params) => asToolResult(await executeCode(params, {
    allowWrites: ALLOW_WRITES, maxControl: MAX_CONTROL, call: bridgeCall,
  })));

  return server;
}

const mcpHandler = createMcpHandler(buildServer);
const nodeMcpHandler = toNodeHandler(mcpHandler);

const httpServer = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

  if (url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({
      ok: true,
      bridge: "cadgrounded-solidworks-bridge",
      version: "0.3.0",
      writes_enabled: ALLOW_WRITES,
      max_control_enabled: MAX_CONTROL,
    }));
    return;
  }

  if (url.pathname === "/mcp") {
    await nodeMcpHandler(req, res);
    return;
  }

  res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ error: "not_found" }));
});

httpServer.listen(PORT, HOST, () => {
  console.log(`CADGrounded SolidWorks MCP v0.3.0 listening on http://${HOST}:${PORT}/mcp`);
  console.log(`Writes enabled: ${ALLOW_WRITES ? "YES" : "NO (recommended for first acceptance)"}`);
});
