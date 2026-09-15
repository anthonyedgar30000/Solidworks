import { execFile } from "node:child_process";

export const CAD_ASK_PATH = "C:\\ChatGPT\\Solidworks\\agent-registry\\cad-ask.ps1";

function defaultRun(file, args, options) {
  return new Promise((resolve, reject) => {
    execFile(file, args, options, (error, stdout, stderr) => {
      if (error) {
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

export async function readCadIntent(
  { request },
  { run = defaultRun, scriptPath = CAD_ASK_PATH } = {},
) {
  const fail = (Code, Message) => ({ Ok: false, Error: { Code, Message } });
  const args = [
    "-NoLogo", "-NoProfile", "-NonInteractive", "-File", scriptPath,
    "-Prompt", request, "-WaitSeconds", "30", "-Json",
  ];

  let output;
  try {
    output = await run("powershell.exe", args, {
      windowsHide: true,
      shell: false,
      timeout: 240000,
      maxBuffer: 16 * 1024 * 1024,
      encoding: "utf8",
    });
  } catch (error) {
    const detail = String(error?.stderr ?? error?.message ?? "").trim();
    return fail(
      error?.killed ? "CAD_INTENT_TIMEOUT" : "CAD_INTENT_FAILED",
      `${detail || "cad-ask.ps1 failed."} No automatic retry was attempted.`,
    );
  }

  const text = String(output?.stdout ?? "").trim();
  if (!text) return fail("CAD_INTENT_EMPTY_RESULT", "cad-ask.ps1 returned no JSON snapshot.");

  try {
    const snapshot = JSON.parse(text);
    if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) {
      throw new Error("Result is not one JSON object.");
    }
    if (!["sw.status", "sw.query_components"].includes(snapshot.command)) {
      throw new Error("Result command is outside the read-intent allowlist.");
    }
    if (snapshot.state !== "completed" || snapshot.data == null) {
      throw new Error("Result is not a completed CAD snapshot.");
    }
    return { Ok: true, Result: snapshot };
  } catch (error) {
    return fail("CAD_INTENT_INVALID_RESULT", `Rejected cad-ask.ps1 output: ${error.message}`);
  }
}
