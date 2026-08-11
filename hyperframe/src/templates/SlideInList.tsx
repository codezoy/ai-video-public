import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill, interpolate, Easing } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius } from "../theme/designTokens";
import { fadeIn, staggerDelay } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface SlideInListProps {
  title?: string;
  items: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const SlideInList: React.FC<SlideInListProps> = ({
  title,
  items,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const displayItems = items.slice(0, 6);

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
          maxWidth: 1300,
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
            gap: spacing.md,
          }}
        >
          {displayItems.map((item, i) => {
            const delay = staggerDelay(i, unit * 0.5);
            const startFrame = unit * 0.8 + delay;
            const itemX = interpolate(frame, [startFrame, startFrame + unit], [-160, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            const itemOpacity = fadeIn(frame, startFrame, unit);

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "row",
                  alignItems: "center",
                  gap: spacing.lg,
                  opacity: itemOpacity,
                  transform: `translateX(${itemX}px)`,
                  backgroundColor: colors.surface,
                  borderRadius: radius.md,
                  padding: `${spacing.md}px ${spacing.lg}px`,
                  borderLeft: `4px solid ${i % 2 === 0 ? accent : colors.panelRight}`,
                }}
              >
                <span
                  style={{
                    color: i % 2 === 0 ? accent : colors.panelRight,
                    fontSize: typography.label.fontSize,
                    fontWeight: 800,
                    minWidth: 32,
                    textAlign: "center",
                  }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div
                  style={{
                    width: 1,
                    height: 32,
                    backgroundColor: colors.border,
                    flexShrink: 0,
                  }}
                />
                <p
                  style={{
                    color: text,
                    fontSize: typography.card.fontSize,
                    fontWeight: 500,
                    lineHeight: 1.4,
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
