import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius, shadow } from "../theme/designTokens";
import { fadeIn, slideUp, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface GlassCardsProps {
  title?: string;
  items: string[];
  icons?: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const GlassCards: React.FC<GlassCardsProps> = ({
  title,
  items,
  icons = [],
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayItems = items.slice(0, 4);

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
      {/* Background radial glow */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse 80% 60% at 50% 50%, ${accent}12 0%, transparent 70%)`,
        }}
      />

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

        {/* Glass card grid */}
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
            const delay = staggerDelay(i, unit * 0.8);
            const cardOpacity = fadeIn(frame, unit + delay, unit);
            const cardY = slideUp(frame, unit + delay, unit, 50);

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
                  background: `linear-gradient(135deg, ${colors.surface}CC 0%, ${colors.surface}88 100%)`,
                  border: `1.5px solid ${accent}30`,
                  backdropFilter: "blur(20px)",
                  boxShadow: `${shadow.card}, inset 0 1px 0 ${accent}20`,
                  opacity: cardOpacity,
                  transform: `translateY(${cardY}px)`,
                }}
              >
                {icons[i] && (
                  <div
                    style={{
                      fontSize: 52,
                      lineHeight: 1,
                    }}
                  >
                    {icons[i]}
                  </div>
                )}
                <p
                  style={{
                    color: text,
                    fontSize: typography.card.fontSize,
                    fontWeight: typography.card.fontWeight,
                    lineHeight: 1.4,
                    margin: 0,
                    textAlign: "center",
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
