// 1920x1080 landscape canvas safe area constants
// Note: canvas is landscape (Root.tsx CANVAS_W=1920, CANVAS_H=1080)
export const SAFE_AREA = {
  top: 60,
  bottom: 60,
  left: 80,
  right: 80,
  safeHeight: 960,  // 1080 - top - bottom
  safeWidth: 1760,  // 1920 - left - right
} as const;

export type LayoutStatus = "SAFE" | "WARNING" | "FAIL";
