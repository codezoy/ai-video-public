import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface SummaryCardProps {
  takeaways: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const SummaryCard: React.FC<SummaryCardProps> = ({
  takeaways,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const titleY = slideUp(frame, 0, unit);

  const itemFontSize = takeaways.length <= 3 ? 34 : 30;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: font_title,
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
        gap: spacing.xl,
      }}
    >
      {/* Heading with accent bar */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.md,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        <div
          style={{
            color: accent,
            fontSize: typography.label.fontSize,
            fontWeight: 700,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
          }}
        >
          KEY TAKEAWAYS
        </div>
        <h2
          style={{
            color: text,
            fontSize: typography.section.fontSize,
            fontWeight: typography.section.fontWeight,
            margin: 0,
            textAlign: "center",
            letterSpacing: typography.section.letterSpacing,
          }}
        >
          핵심 요약
        </h2>
      </div>

      {/* Takeaway list */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: spacing.md,
          width: "100%",
          maxWidth: 1280,
        }}
      >
        {takeaways.map((item, i) => {
          const start = unit + i * Math.round(unit * 0.7);
          const opacity = fadeIn(frame, start, unit);
          const y = slideUp(frame, start, unit, 28);

          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: spacing.lg,
                opacity,
                transform: `translateY(${y}px)`,
                padding: `${spacing.lg}px ${spacing.xl}px`,
                border: `1.5px solid ${accent}25`,
                borderRadius: radius.lg,
                backgroundColor: colors.surface,
                boxShadow: shadow.card,
              }}
            >
              {/* Check badge */}
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: radius.full,
                  backgroundColor: `${accent}20`,
                  border: `2px solid ${accent}50`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: accent,
                  fontSize: 26,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                ✓
              </div>
              {/* Text */}
              <div
                style={{
                  color: text,
                  fontSize: itemFontSize,
                  fontWeight: 500,
                  lineHeight: 1.55,
                  letterSpacing: "-0.01em",
                  wordBreak: "keep-all",
                }}
              >
                {item}
              </div>
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
