import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius } from "../theme/designTokens";
import { fadeIn, slideUp, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface BorderCardsProps {
  title?: string;
  items: string[];
  labels?: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const BorderCards: React.FC<BorderCardsProps> = ({
  title,
  items,
  labels = [],
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayItems = items.slice(0, 4);

  const cardColors = [accent, colors.panelRight, colors.cardPalette[2], colors.cardPalette[3]];

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
            const delay = staggerDelay(i, unit * 0.7);
            const cardOpacity = fadeIn(frame, unit + delay, unit);
            const cardY = slideUp(frame, unit + delay, unit, 40);
            const borderColor = cardColors[i % cardColors.length];

            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  maxWidth: 380,
                  display: "flex",
                  flexDirection: "column",
                  gap: spacing.sm,
                  padding: `${spacing.lg}px`,
                  borderRadius: radius.lg,
                  backgroundColor: colors.surface,
                  border: `2.5px solid ${borderColor}`,
                  opacity: cardOpacity,
                  transform: `translateY(${cardY}px)`,
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                {/* Top accent stripe */}
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 4,
                    backgroundColor: borderColor,
                  }}
                />

                {labels[i] && (
                  <div
                    style={{
                      color: borderColor,
                      fontSize: typography.label.fontSize,
                      fontWeight: 700,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      marginTop: spacing.xs,
                    }}
                  >
                    {labels[i]}
                  </div>
                )}

                <p
                  style={{
                    color: text,
                    fontSize: typography.card.fontSize,
                    fontWeight: typography.card.fontWeight,
                    lineHeight: 1.45,
                    margin: 0,
                    wordBreak: "keep-all",
                  }}
                >
                  {item}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
