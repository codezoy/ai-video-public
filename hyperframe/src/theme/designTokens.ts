// Modern Lecture Design System — single source of truth for all visual tokens.
// Color palette: premium dark (#0D0D14 base) — near-black for high-contrast lecture aesthetic.

export const colors = {
  bg: "#0D0D14",
  surface: "#1C1E2E",
  secondary: "#6E7491",
  accent: "#C9ADA7",
  text: "#F0EFE9",

  // Semantic aliases
  border: "#2A2D3E",
  borderStrong: "#3E4260",
  overlay: "#0D0D14cc",

  // Card palette — harmonious with bg, used for icon-card backgrounds
  cardPalette: [
    "#C9ADA7", // warm beige
    "#8B9DC3", // steel blue-purple
    "#9A8C98", // purple-gray
    "#B5C0C8", // cool slate
    "#C4B5A5", // warm stone
    "#A8B8C8", // mist blue
  ],

  // Comparison panel pair (CompareTwo left/right)
  panelLeft: "#C9ADA7",
  panelRight: "#8B9DC3",
} as const;

export const typography = {
  hero: {
    fontSize: 128,
    fontWeight: 800,
    letterSpacing: "-0.03em",
    lineHeight: 1.05,
  },
  section: {
    fontSize: 72,
    fontWeight: 700,
    letterSpacing: "-0.02em",
    lineHeight: 1.15,
  },
  card: {
    fontSize: 44,
    fontWeight: 700,
    letterSpacing: "-0.01em",
    lineHeight: 1.25,
  },
  body: {
    fontSize: 36,
    fontWeight: 400,
    letterSpacing: "0",
    lineHeight: 1.6,
  },
  caption: {
    fontSize: 28,
    fontWeight: 600,
    letterSpacing: "0.01em",
    lineHeight: 1.5,
  },
  label: {
    fontSize: 22,
    fontWeight: 600,
    letterSpacing: "0.1em",
    lineHeight: 1.4,
  },
} as const;

export const spacing = {
  xs: 8,
  sm: 16,
  md: 28,
  lg: 44,
  xl: 64,
  xxl: 96,
  section: 120,
} as const;

export const radius = {
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  full: 9999,
} as const;

// Shadows — designed for dark near-black bg
export const shadow = {
  card: "0 4px 32px rgba(0,0,0,0.55)",
  elevated: "0 8px 48px rgba(0,0,0,0.65)",
  glow: (hex: string, alpha = "18") => `0 0 40px ${hex}${alpha}`,
} as const;

export const motion = {
  unitMs: 300,
  fastMs: 150,
  slowMs: 500,
} as const;

export const fonts = {
  title: "Paperlogy, Pretendard, 'Noto Sans SC', sans-serif",
  body: "Pretendard, 'Noto Sans SC', sans-serif",
  code: "JetBrains Mono",
} as const;

// Convenience bundle
export const ds = {
  colors,
  typography,
  spacing,
  radius,
  shadow,
  motion,
  fonts,
} as const;
