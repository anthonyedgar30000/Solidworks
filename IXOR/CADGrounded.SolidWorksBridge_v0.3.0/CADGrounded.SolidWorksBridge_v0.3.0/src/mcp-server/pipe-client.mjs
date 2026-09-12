import net from "node:net";
import { randomUUID } from "node:crypto";

export const PIPE_NAME = "\\\\.\\pipe\\CADGrounded.SolidWorksBridge.v0.1";

export async function bridgeCall(method, params = {}, { timeoutMs = 8000 } = {}) {
  const request = {
    Id: randomUUID(),
    Method: method,
    Params: params,
  };

  return await new Promise((resolve, reject) => {
    const socket = net.createConnection(PIPE_NAME);
    let buffer = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      socket.destroy();
      reject(new Error(`SOLIDWORKS bridge timed out after ${timeoutMs} ms.`));
    }, timeoutMs);

    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.end();
      fn(value);
    };

    socket.setEncoding("utf8");

    socket.on("connect", () => {
      socket.write(`${JSON.stringify(request)}\n`);
    });

    socket.on("data", (chunk) => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0) return;

      const line = buffer.slice(0, newline).trim();
      if (!line) return;

      try {
        const response = JSON.parse(line);
        finish(resolve, response);
      } catch (error) {
        finish(reject, new Error(`Invalid JSON from SOLIDWORKS bridge: ${error.message}`));
      }
    });

    socket.on("error", (error) => {
      finish(reject, new Error(
        `Cannot reach SOLIDWORKS named pipe ${PIPE_NAME}. ` +
        `Is SOLIDWORKS running with the CADGrounded add-in loaded? ${error.message}`
      ));
    });

    socket.on("end", () => {
      if (!settled && buffer.trim().length === 0) {
        finish(reject, new Error("SOLIDWORKS bridge closed the pipe without a response."));
      }
    });
  });
}
