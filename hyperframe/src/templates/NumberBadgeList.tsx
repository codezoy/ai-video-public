import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius } from "../theme/designTokens";
import { fadeIn, slideUp, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface NumberBadgeListProps {
  title?: string;
  items: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const NumberBadgeList: React.FC<NumberBadgeListProps> = ({
  title,
  items,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayItems = items.slice(0, 5);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        fontFamily: font_title,
        overflow: "hidden",
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: spacing.xl,
          maxWidth: 1400,
        }}
      >
        {title && (
          <h2
            style={{
              color: accent,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              letterSpacing: typography.section.letterSpacing,
              margin: 0,
              opacity: titleOpacity,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        )}

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: spacing.lg,
          }}
        >
          {displayItems.map((item, i) => {
            const delay = staggerDelay(i, unit * 0.6);
            const itemOpacity = fadeIn(frame, unit + delay, unit);
            const itemY = slideUp(frame, unit + delay, unit, 30);

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "row",
                  alignItems: "center",
                  gap: spacing.xl,
                  opacity: itemOpacity,
                  transform: `translateY(${itemY}px)`,
                }}
              >
                {/* Large number badge */}
                <div
                  style={{
                    width: 100,
                    height: 100,
                    borderRadius: radius.full,
                    backgroundColor: `${accent}18`,
                    border: `2px solid ${accent}60`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      color: accent,
                      fontSize: 52,
                      fontWeight: 800,
                      lineHeight: 1,
                    }}
                  >
                    {i + 1}
                  </span>
                </div>

                {/* Item text */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}
                >
                  <p
                    style={{
                      color: text,
                      fontSize: typography.card.fontSize,
                      fontWeight: typography.card.fontWeight,
                      lineHeight: 1.4,
                      margin: 0,
                      wordBreak: "keep-all",
                    }}
                  >
                    {item}
                  </p>
                  <div
                    style={{
                      width: 200,
                      height: 2,
                      backgroundColor: colors.border,
                      borderRadius: 1,
                    }}
                  />
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
