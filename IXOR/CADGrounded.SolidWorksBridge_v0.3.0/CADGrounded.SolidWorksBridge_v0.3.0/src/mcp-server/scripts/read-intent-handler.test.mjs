import test from "node:test";
import assert from "node:assert/strict";
import { CAD_ASK_PATH, readCadIntent } from "../read-intent-handler.mjs";

const snapshot = {
  job_id: "job-1",
  command: "sw.status",
  state: "completed",
  data: { active_document: null },
};

test("invokes only the fixed script once without a shell", async () => {
  let calls = 0;
  const request = "-NoProfile; Write-Output never";
  const result = await readCadIntent({ request }, { run: async (file, args, options) => {
    calls++;
    assert.equal(file, "powershell.exe");
    assert.deepEqual(args, [
      "-NoLogo", "-NoProfile", "-NonInteractive", "-File", CAD_ASK_PATH,
      "-Prompt", request, "-WaitSeconds", "30", "-Json",
    ]);
    assert.equal(options.shell, false);
    return { stdout: JSON.stringify(snapshot), stderr: "" };
  }});
  assert.equal(calls, 1);
  assert.equal(result.Ok, true);
  assert.deepEqual(result.Result, snapshot);
});

test("accepts only allowlisted completed snapshots", async () => {
  for (const value of [
    { ...snapshot, command: "sw.set_transform" },
    { ...snapshot, state: "queued" },
    { ...snapshot, data: null },
    [snapshot],
  ]) {
    const result = await readCadIntent({ request: "status" }, {
      run: async () => ({ stdout: JSON.stringify(value), stderr: "" }),
    });
    assert.equal(result.Error.Code, "CAD_INTENT_INVALID_RESULT");
  }
});

test("rejects empty and malformed output", async () => {
  for (const stdout of ["", "not json"] ) {
    const result = await readCadIntent({ request: "status" }, {
      run: async () => ({ stdout, stderr: "" }),
    });
    assert.match(result.Error.Code, /^CAD_INTENT_(EMPTY|INVALID)_RESULT$/);
  }
});

test("process failures are returned once with no retry", async () => {
  let calls = 0;
  const result = await readCadIntent({ request: "status" }, { run: async () => {
    calls++;
    const error = new Error("failed");
    error.stderr = "blocked";
    throw error;
  }});
  assert.equal(calls, 1);
  assert.equal(result.Error.Code, "CAD_INTENT_FAILED");
  assert.match(result.Error.Message, /No automatic retry/);
});

test("timeouts are explicit and never retried", async () => {
  let calls = 0;
  const result = await readCadIntent({ request: "status" }, { run: async () => {
    calls++;
    const error = new Error("timed out");
    error.killed = true;
    throw error;
  }});
  assert.equal(calls, 1);
  assert.equal(result.Error.Code, "CAD_INTENT_TIMEOUT");
});
