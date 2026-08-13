import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { radius, shadow, spacing, typography, colors } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface FlowStepsProps {
  title: string;
  category?: string;
  steps: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const FlowSteps: React.FC<FlowStepsProps> = ({
  title,
  category,
  steps,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);
  const count = Math.max(1, steps.length);
  const compact = count >= 6;
  const gap = compact ? spacing.sm : spacing.md;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        fontFamily: font_title,
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom + 96}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "grid",
          gridTemplateRows: "auto 1fr",
          rowGap: spacing.lg,
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          {category && (
            <div
              style={{
                color: accent,
                fontSize: typography.label.fontSize,
                fontWeight: 700,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                opacity: fadeIn(frame, 0, unit),
                transform: `translateY(${slideUp(frame, 0, unit, 16)}px)`,
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
              opacity: fadeIn(frame, Math.round(unit * 0.4), unit),
              transform: `translateY(${slideUp(frame, Math.round(unit * 0.4), unit)}px)`,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        </div>

        <div
          style={{
            width: "100%",
            display: "grid",
            gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`,
            columnGap: gap,
            alignItems: "stretch",
            position: "relative",
          }}
        >
          {steps.map((step, i) => {
            const stepStart = unit + i * Math.round(unit * 0.55);
            const lines = String(step).split("\n");
            const mainLabel = lines[0];
            const subLabel = lines.slice(1).join(" ");
            const hasArrow = i < steps.length - 1;

            return (
              <div
                key={i}
                style={{
                  opacity: fadeIn(frame, stepStart, unit),
                  transform: `translateY(${slideUp(frame, stepStart, unit, 28)}px)`,
                  minWidth: 0,
                  display: "grid",
                  gridTemplateRows: "56px minmax(170px, 1fr)",
                  rowGap: spacing.sm,
                  position: "relative",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    position: "relative",
                  }}
                >
                  {hasArrow && (
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        right: `calc(-50% - ${gap / 2}px)`,
                        height: 3,
                        backgroundColor: `${accent}55`,
                        top: 26,
                      }}
                    />
                  )}
                  <div
                    style={{
                      width: compact ? 46 : 56,
                      height: compact ? 46 : 56,
                      borderRadius: radius.full,
                      backgroundColor: accent,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: bg,
                      fontSize: compact ? 22 : 26,
                      fontWeight: 800,
                      boxShadow: shadow.glow(accent, "30"),
                      zIndex: 2,
                    }}
                  >
                    {i + 1}
                  </div>
                  {hasArrow && (
                    <div
                      style={{
                        position: "absolute",
                        left: `calc(100% + ${gap / 2 - 18}px)`,
                        top: 11,
                        width: 36,
                        height: 34,
                        borderRadius: radius.full,
                        backgroundColor: bg,
                        border: `1px solid ${colors.borderStrong}`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: accent,
                        fontSize: 24,
                        zIndex: 3,
                      }}
                    >
                      →
                    </div>
                  )}
                </div>

                <div
                  style={{
                    color: text,
                    fontSize: compact ? 24 : 32,
                    fontWeight: 700,
                    textAlign: "center",
                    padding: `${compact ? spacing.md : spacing.lg}px ${compact ? spacing.sm : spacing.md}px`,
                    border: `1.5px solid ${accent}30`,
                    borderRadius: radius.lg,
                    backgroundColor: colors.surface,
                    boxShadow: shadow.card,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: spacing.xs,
                    minWidth: 0,
                    wordBreak: "keep-all",
                  }}
                >
                  <span style={{ fontWeight: 700, lineHeight: 1.3 }}>{mainLabel}</span>
                  {subLabel && (
                    <span
                      style={{
                        fontSize: compact ? 18 : 24,
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
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
