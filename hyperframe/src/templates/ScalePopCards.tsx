import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill, interpolate, Easing } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius, shadow } from "../theme/designTokens";
import { fadeIn, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface ScalePopCardsProps {
  title?: string;
  items: string[];
  values?: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const ScalePopCards: React.FC<ScalePopCardsProps> = ({
  title,
  items,
  values = [],
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayItems = items.slice(0, 4);

  const cardColors = [
    { bg: `${accent}15`, border: accent, value: accent },
    { bg: `${colors.panelRight}15`, border: colors.panelRight, value: colors.panelRight },
    { bg: `${colors.cardPalette[2]}15`, border: colors.cardPalette[2], value: colors.cardPalette[2] },
    { bg: `${colors.cardPalette[3]}15`, border: colors.cardPalette[3], value: colors.cardPalette[3] },
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
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.xl,
          padding: `${SAFE_AREA.top}px ${SAFE_AREA.left}px`,
          width: "100%",
          maxWidth: 1760,
        }}
      >
        {title && (
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              margin: 0,
              opacity: titleOpacity,
              textAlign: "center",
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        )}

        <div
          style={{
            display: "flex",
            flexDirection: "row",
            gap: spacing.lg,
            width: "100%",
            justifyContent: "center",
          }}
        >
          {displayItems.map((item, i) => {
            const delay = staggerDelay(i, unit * 0.6);
            const startFrame = unit * 0.5 + delay;
            const cardScale = interpolate(frame, [startFrame, startFrame + unit], [0.6, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.back(1.5)),
            });
            const cardOpacity = fadeIn(frame, startFrame, unit * 0.7);
            const palette = cardColors[i % cardColors.length];

            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  maxWidth: 380,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: spacing.md,
                  padding: `${spacing.xl}px ${spacing.lg}px`,
                  borderRadius: radius.xl,
                  backgroundColor: palette.bg,
                  border: `2px solid ${palette.border}50`,
                  boxShadow: shadow.card,
                  opacity: cardOpacity,
                  transform: `scale(${cardScale})`,
                }}
              >
                {values[i] && (
                  <div
                    style={{
                      color: palette.value,
                      fontSize: 72,
                      fontWeight: 900,
                      lineHeight: 1,
                      letterSpacing: "-0.04em",
                    }}
                  >
                    {values[i]}
                  </div>
                )}
                <p
                  style={{
                    color: text,
                    fontSize: typography.card.fontSize,
                    fontWeight: values[i] ? 500 : 600,
                    lineHeight: 1.4,
                    margin: 0,
                    textAlign: "center",
                    wordBreak: "keep-all",
                  }}
                >
                  {item}
                </p>
                {/* Bottom accent line */}
                <div
                  style={{
                    width: 40,
                    height: 3,
                    backgroundColor: palette.border,
                    borderRadius: 2,
                    marginTop: spacing.xs,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
