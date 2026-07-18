export const pctFmt = (x) =>
  x == null ? "—" : `${(x * 100).toFixed(0)}%`;

export const f3 = (x) => (x == null ? "—" : x.toFixed(3));

export const ms = (x) => (x == null ? "—" : `${Math.round(x).toLocaleString()} ms`);

export const shortModel = (id) => id.split("/").pop();

export const methodLabel = { json_mode: "JSON mode", tool_call: "Tool call" };
