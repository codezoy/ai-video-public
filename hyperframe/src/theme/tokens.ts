// Mirrors assets/theme.json — single source of truth for Python side.
// Keep in sync manually when assets/theme.json changes.
// Color palette: Premium lecture dark — near-black base, warm white text.
export const tokens = {
  bg: "#0D0D14",
  surface: "#1C1E2E",
  secondary: "#6E7491",
  accent: "#C9ADA7",
  text: "#F0EFE9",
  font_title: "Paperlogy, Pretendard, 'Noto Sans SC', sans-serif",
  font_code: "JetBrains Mono",
  timing_unit_ms: 300,
  fps: 30,
} as const;

export const {
  bg,
  surface,
  secondary,
  accent,
  text,
  font_title,
  font_code,
  timing_unit_ms,
  fps,
} = tokens;
