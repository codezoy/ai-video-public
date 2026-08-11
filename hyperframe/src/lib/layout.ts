import { SAFE_AREA, type LayoutStatus } from "./safearea";

export interface ContentBounds {
  width: number;
  height: number;
}

export interface OverflowResult {
  overflow: boolean;
  overflowPx: number;
  status: LayoutStatus;
}

/** Estimate total content bounds from item count, per-item height, and gap. */
export function calculateContentBounds(
  itemCount: number,
  itemHeight: number,
  gap: number
): ContentBounds {
  return {
    width: SAFE_AREA.safeWidth,
    height: itemCount * itemHeight + Math.max(0, itemCount - 1) * gap,
  };
}

/**
 * Calculate the scale factor needed to fit content within the safe area.
 * Returns a value ≤ 1; returns 1 when content already fits.
 */
export function calculateScaleFactor(
  contentHeight: number,
  contentWidth: number = SAFE_AREA.safeWidth
): number {
  const scaleH = contentHeight > 0 ? Math.min(1, SAFE_AREA.safeHeight / contentHeight) : 1;
  const scaleW = contentWidth > 0 ? Math.min(1, SAFE_AREA.safeWidth / contentWidth) : 1;
  return Math.min(scaleH, scaleW);
}

/**
 * Calculate the top/left offset to center scaled content within the safe area.
 * Use this when manually positioning content with absolute layout.
 */
export function calculateCenterOffset(
  contentHeight: number,
  scale: number
): { x: number; y: number } {
  const scaledHeight = contentHeight * scale;
  return {
    x: 0,
    y: Math.max(0, (SAFE_AREA.safeHeight - scaledHeight) / 2),
  };
}

/** Check whether content exceeds safe area bounds. */
export function isOverflow(
  contentHeight: number,
  contentWidth: number = SAFE_AREA.safeWidth
): OverflowResult {
  const overflowPx = Math.max(
    contentHeight - SAFE_AREA.safeHeight,
    contentWidth - SAFE_AREA.safeWidth,
    0
  );
  const overflow = overflowPx > 0;
  const status: LayoutStatus = overflow
    ? overflowPx <= 120
      ? "WARNING"
      : "FAIL"
    : "SAFE";
  return { overflow, overflowPx, status };
}

/**
 * Compute CSS marginTop/marginBottom to compensate for transform:scale().
 * Applying these negative margins makes flex layout treat the element as its
 * visually-scaled size instead of its original unscaled size, allowing correct
 * flex centering when scale < 1.
 *
 * Usage:
 *   const scale = calculateScaleFactor(contentH);
 *   const negMargin = scaleCompensationMargin(contentH, scale);
 *   // apply: marginTop: negMargin, marginBottom: negMargin, transform: `scale(${scale})`
 */
export function scaleCompensationMargin(contentHeight: number, scale: number): number {
  return -(contentHeight * (1 - scale)) / 2;
}
