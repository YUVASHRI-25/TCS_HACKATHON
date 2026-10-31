// Chart colours, validated with the dataviz palette validator on the panel surface (#111830, dark):
// blue/orange pass lightness band, chroma, CVD (ΔE 26.8) and >= 3:1 contrast.
export const VIZ = {
  surface: "#111830",
  primary: "#3987e5", // signal points, magnitudes, ordinary flow
  contrast: "#d95926", // penalties, suspicious flow
  neutral: "#4b5675", // gridlines / non-suspicious context
  text: "#c3c2b7",
  muted: "#8b98b8",
};

// Entity-type node colours for the graph (identity, fixed order; shape carries identity too).
export const NODE_STYLE: Record<string, { color: string; shape: string }> = {
  account: { color: "#3987e5", shape: "ellipse" },
  customer: { color: "#199e70", shape: "round-rectangle" },
  device: { color: "#c98500", shape: "diamond" },
  ip: { color: "#9085e9", shape: "hexagon" },
  merchant: { color: "#d55181", shape: "round-tag" },
  watchlist_entry: { color: "#e66767", shape: "star" },
  prior_alert: { color: "#d95926", shape: "triangle" },
  prior_case: { color: "#d95926", shape: "vee" },
  complaint: { color: "#d55181", shape: "rhomboid" },
  entity: { color: "#8b98b8", shape: "ellipse" },
};
