import test from "node:test";
import assert from "node:assert/strict";
import {
  FULL_TOOL_PROFILE,
  INTENT_READONLY_TOOL_PROFILE,
  resolveServerProfile,
} from "../server-profile.mjs";

test("full is the backward-compatible default profile", () => {
  assert.deepEqual(resolveServerProfile({}), {
    toolProfile: FULL_TOOL_PROFILE,
    exposeDirectTools: true,
    allowWrites: false,
    maxControl: false,
  });
});

test("full profile preserves explicitly requested local gates", () => {
  const profile = resolveServerProfile({
    SWBRIDGE_TOOL_PROFILE: FULL_TOOL_PROFILE,
    SWBRIDGE_ALLOW_WRITES: "1",
    SWBRIDGE_MAX_CONTROL: "1",
  });
  assert.equal(profile.exposeDirectTools, true);
  assert.equal(profile.allowWrites, true);
  assert.equal(profile.maxControl, true);
});

test("intent-readonly hides direct tools and forces both gates off", () => {
  assert.deepEqual(resolveServerProfile({
    SWBRIDGE_TOOL_PROFILE: INTENT_READONLY_TOOL_PROFILE,
    SWBRIDGE_ALLOW_WRITES: "1",
    SWBRIDGE_MAX_CONTROL: "1",
  }), {
    toolProfile: INTENT_READONLY_TOOL_PROFILE,
    exposeDirectTools: false,
    allowWrites: false,
    maxControl: false,
  });
});

test("unknown profiles fail closed at startup", () => {
  assert.throws(
    () => resolveServerProfile({ SWBRIDGE_TOOL_PROFILE: "other" }),
    /Invalid SWBRIDGE_TOOL_PROFILE/,
  );
});
