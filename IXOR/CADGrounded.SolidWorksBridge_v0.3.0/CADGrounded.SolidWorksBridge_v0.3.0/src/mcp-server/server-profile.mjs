export const FULL_TOOL_PROFILE = "full";
export const INTENT_READONLY_TOOL_PROFILE = "intent-readonly";

export function resolveServerProfile(env = process.env) {
  const toolProfile = env.SWBRIDGE_TOOL_PROFILE ?? FULL_TOOL_PROFILE;
  if (![FULL_TOOL_PROFILE, INTENT_READONLY_TOOL_PROFILE].includes(toolProfile)) {
    throw new Error(
      `Invalid SWBRIDGE_TOOL_PROFILE '${toolProfile}'. Use '${FULL_TOOL_PROFILE}' or '${INTENT_READONLY_TOOL_PROFILE}'.`,
    );
  }

  const intentReadonly = toolProfile === INTENT_READONLY_TOOL_PROFILE;
  return {
    toolProfile,
    exposeDirectTools: !intentReadonly,
    allowWrites: !intentReadonly && env.SWBRIDGE_ALLOW_WRITES === "1",
    maxControl: !intentReadonly && env.SWBRIDGE_MAX_CONTROL === "1",
  };
}
