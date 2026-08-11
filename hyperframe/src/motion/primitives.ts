import { interpolate, Easing } from "remotion";

export const EASE_OUT_EXPO = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_OUT_QUART = Easing.bezier(0.25, 1, 0.5, 1);

export function fadeIn(frame: number, start: number, duration: number): number {
  return interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
}

export function fadeOut(
  frame: number,
  start: number,
  duration: number
): number {
  return interpolate(frame, [start, start + duration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

export function slideUp(
  frame: number,
  start: number,
  duration: number,
  distance = 40
): number {
  return interpolate(frame, [start, start + duration], [distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_EXPO,
  });
}

export function slideDown(
  frame: number,
  start: number,
  duration: number,
  distance = 40
): number {
  return interpolate(frame, [start, start + duration], [-distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_EXPO,
  });
}

export function scaleIn(
  frame: number,
  start: number,
  duration: number,
  from = 0.9
): number {
  return interpolate(frame, [start, start + duration], [from, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_EXPO,
  });
}

export function typewriterProgress(
  frame: number,
  start: number,
  charsPerSecond: number,
  fps: number
): number {
  return Math.floor(
    interpolate(frame, [start, start + (charsPerSecond * fps) / charsPerSecond], [0, charsPerSecond], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
}

export function pulse(
  frame: number,
  periodFrames: number,
  amplitude = 0.05
): number {
  return 1 + amplitude * Math.sin((frame / periodFrames) * 2 * Math.PI);
}

export function staggerDelay(index: number, baseDelay: number): number {
  return index * baseDelay;
}
