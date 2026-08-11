import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius } from "../theme/designTokens";
import { fadeIn, slideUp, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface PillTagsProps {
  title?: string;
  tags: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const PillTags: React.FC<PillTagsProps> = ({
  title,
  tags,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayTags = tags.slice(0, 10);

  // Alternate pill styles for visual variety
  const pillStyles = [
    { bg: `${accent}22`, border: accent, color: accent },
    { bg: `${colors.panelRight}22`, border: colors.panelRight, color: colors.panelRight },
    { bg: `${colors.cardPalette[2]}22`, border: colors.cardPalette[2], color: colors.cardPalette[2] },
    { bg: colors.surface, border: colors.border, color: text },
  ];

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: font_title,
        overflow: "hidden",
      }}
    >
      {/* Background scatter dots */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(circle at 30% 70%, ${accent}0A 0%, transparent 50%),
                       radial-gradient(circle at 70% 30%, ${colors.panelRight}0A 0%, transparent 50%)`,
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.xxl,
          padding: `${SAFE_AREA.top}px ${SAFE_AREA.left}px`,
          width: "100%",
          maxWidth: 1600,
        }}
      >
        {title && (
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              letterSpacing: typography.section.letterSpacing,
              margin: 0,
              opacity: titleOpacity,
              textAlign: "center",
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        )}

        {/* Pill tag cloud */}
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            flexWrap: "wrap",
            gap: spacing.md,
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          {displayTags.map((tag, i) => {
            const delay = staggerDelay(i, unit * 0.4);
            const tagOpacity = fadeIn(frame, unit * 0.5 + delay, unit);
            const tagY = slideUp(frame, unit * 0.5 + delay, unit, 20);
            const style = pillStyles[i % pillStyles.length];
            const isLarge = i % 3 === 0;

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: `${isLarge ? 18 : 14}px ${isLarge ? 40 : 32}px`,
                  borderRadius: radius.full,
                  backgroundColor: style.bg,
                  border: `2px solid ${style.border}60`,
                  opacity: tagOpacity,
                  transform: `translateY(${tagY}px)`,
                }}
              >
                <span
                  style={{
                    color: style.color,
                    fontSize: isLarge ? typography.card.fontSize : typography.body.fontSize,
                    fontWeight: isLarge ? 700 : 600,
                    letterSpacing: "-0.01em",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tag}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
