import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, surface, font_title } from "../theme/tokens";
import { radius, shadow, spacing, typography, colors } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";
import { calculateScaleFactor, isOverflow, scaleCompensationMargin } from "../lib/layout";

export interface FlowStepsProps {
  title: string;
  category?: string;
  steps: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

const ARROW = "→";
const HORIZONTAL_MAX = 4;

const TITLE_H = 80;
const CATEGORY_H = 36;
const OUTER_GAP = 60;
const STEP_ITEM_H = 200;
const ARROW_H = 40;
const STEPS_GAP = 24;
// Extra bottom clearance for caption overlay (safeAreaBottom=80 + captionHeight≈70)
const CAPTION_BOTTOM_CLEARANCE = 150;

function estimateVerticalContentHeight(stepCount: number, hasCategory: boolean): number {
  const headerH = TITLE_H + (hasCategory ? CATEGORY_H + 12 : 0);
  const stepsH =
    stepCount * STEP_ITEM_H +
    (stepCount - 1) * ARROW_H +
    (2 * stepCount - 2) * STEPS_GAP;
  return headerH + OUTER_GAP + stepsH;
}

export const FlowSteps: React.FC<FlowStepsProps> = ({
  title,
  category,
  steps,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const categoryOpacity = fadeIn(frame, 0, unit);
  const categoryY = slideUp(frame, 0, unit, 16);
  const titleOpacity = fadeIn(frame, Math.round(unit * 0.4), unit);
  const titleY = slideUp(frame, Math.round(unit * 0.4), unit);

  const isHorizontal = steps.length <= HORIZONTAL_MAX;

  // For vertical layout: reduce available height to prevent caption overlap
  const availableH = isHorizontal
    ? SAFE_AREA.safeHeight
    : SAFE_AREA.safeHeight - CAPTION_BOTTOM_CLEARANCE;
  const contentH = isHorizontal ? 0 : estimateVerticalContentHeight(steps.length, !!category);
  const scale = isHorizontal ? 1 : Math.min(1, availableH / contentH);
  const negMargin = isHorizontal ? 0 : scaleCompensationMargin(contentH, scale);

  if (!isHorizontal) {
    const { status, overflowPx } = isOverflow(contentH);
    if (status !== "SAFE") {
      console.log(
        `[LAYOUT_${status}] template=flow_steps content_height=${Math.round(contentH)} overflow=${Math.round(overflowPx)}`
      );
    }
  }

  const stepCardW = isHorizontal
    ? steps.length <= 3 ? 340 : steps.length === 4 ? 280 : 240
    : 800;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: font_title,
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${isHorizontal ? SAFE_AREA.bottom : SAFE_AREA.bottom + CAPTION_BOTTOM_CLEARANCE}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: OUTER_GAP,
          width: "100%",
          transform: `scale(${scale})`,
          transformOrigin: "center center",
          marginTop: negMargin,
          marginBottom: negMargin,
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          {category && (
            <div
              style={{
                color: accent,
                fontSize: typography.label.fontSize,
                fontWeight: 700,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                opacity: categoryOpacity,
                transform: `translateY(${categoryY}px)`,
              }}
            >
              {category}
            </div>
          )}
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              margin: 0,
              textAlign: "center",
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              letterSpacing: typography.section.letterSpacing,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        </div>

        {/* Steps */}
        <div
          style={{
            display: "flex",
            flexDirection: isHorizontal ? "row" : "column",
            alignItems: "center",
            gap: isHorizontal ? 0 : STEPS_GAP,
            width: "100%",
            justifyContent: "center",
          }}
        >
          {steps.map((step, i) => {
            const stepStart = unit + i * unit;
            const stepOpacity = fadeIn(frame, stepStart, unit);
            const stepY = slideUp(frame, stepStart, unit, 32);
            const arrowStart = unit + i * unit + Math.round(unit * 0.5);
            const arrowOpacity = fadeIn(frame, arrowStart, Math.round(unit * 0.5));

            const lines = step.split("\n");
            const mainLabel = lines[0];
            const subLabel = lines[1] ?? "";

            return (
              <React.Fragment key={i}>
                {/* Step box */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: spacing.sm,
                    opacity: stepOpacity,
                    transform: `translateY(${stepY}px)`,
                  }}
                >
                  {/* Step number badge */}
                  <div
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: radius.full,
                      backgroundColor: accent,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: bg,
                      fontSize: 26,
                      fontWeight: 800,
                      boxShadow: shadow.glow(accent, "30"),
                    }}
                  >
                    {i + 1}
                  </div>
                  {/* Step label card */}
                  <div
                    style={{
                      color: text,
                      fontSize: isHorizontal ? 32 : 38,
                      fontWeight: 700,
                      textAlign: "center",
                      width: stepCardW,
                      padding: `${spacing.lg}px ${spacing.md}px`,
                      border: `1.5px solid ${accent}30`,
                      borderRadius: radius.lg,
                      backgroundColor: colors.surface,
                      boxShadow: shadow.card,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: spacing.xs,
                      minHeight: isHorizontal ? 120 : 100,
                      justifyContent: "center",
                    }}
                  >
                    <span style={{ fontWeight: 700, lineHeight: 1.3 }}>{mainLabel}</span>
                    {subLabel && (
                      <span
                        style={{
                          fontSize: isHorizontal ? 24 : 28,
                          fontWeight: 400,
                          color: `${text}99`,
                          lineHeight: 1.4,
                        }}
                      >
                        {subLabel}
                      </span>
                    )}
                  </div>
                </div>

                {/* Arrow */}
                {i < steps.length - 1 && (
                  <div
                    style={{
                      color: accent,
                      fontSize: isHorizontal ? 48 : 36,
                      fontWeight: 400,
                      opacity: arrowOpacity,
                      margin: isHorizontal ? "0 20px" : "0",
                      alignSelf: "center",
                      transform: isHorizontal ? "none" : "rotate(90deg)",
                      lineHeight: 1,
                      marginTop: isHorizontal ? 28 : 0,
                    }}
                  >
                    {ARROW}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
