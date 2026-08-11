import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface SplitTitleProps {
  title: string;
  subtitle?: string;
  detail?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const SplitTitle: React.FC<SplitTitleProps> = ({
  title,
  subtitle = "",
  detail = "",
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const dividerOpacity = fadeIn(frame, 0, unit * 2);
  const leftOpacity = fadeIn(frame, unit, unit);
  const leftY = slideUp(frame, unit, unit, 30);
  const rightOpacity = fadeIn(frame, unit * 2, unit);
  const rightY = slideUp(frame, unit * 2, unit, 30);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "row",
        fontFamily: font_title,
        overflow: "hidden",
      }}
    >
      {/* Left panel — title dominant */}
      <div
        style={{
          flex: 6,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: `${SAFE_AREA.top}px ${spacing.xl}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
          opacity: leftOpacity,
          transform: `translateY(${leftY}px)`,
        }}
      >
        {subtitle && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginBottom: spacing.md,
            }}
          >
            {subtitle}
          </div>
        )}
        <h1
          style={{
            color: text,
            fontSize: 96,
            fontWeight: 800,
            lineHeight: 1.08,
            margin: 0,
            letterSpacing: "-0.03em",
            wordBreak: "keep-all",
          }}
        >
          {title}
        </h1>
      </div>

      {/* Vertical divider */}
      <div
        style={{
          width: 3,
          backgroundColor: accent,
          margin: `${SAFE_AREA.top * 2}px 0`,
          opacity: dividerOpacity * 0.6,
          borderRadius: 2,
        }}
      />

      {/* Right panel — detail */}
      <div
        style={{
          flex: 4,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${spacing.xl}px`,
          opacity: rightOpacity,
          transform: `translateY(${rightY}px)`,
        }}
      >
        {detail ? (
          <p
            style={{
              color: colors.secondary,
              fontSize: typography.body.fontSize,
              lineHeight: 1.7,
              margin: 0,
              wordBreak: "keep-all",
            }}
          >
            {detail}
          </p>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: spacing.sm,
            }}
          >
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  height: 3,
                  backgroundColor: colors.borderStrong,
                  borderRadius: 2,
                  width: i === 2 ? "60%" : "100%",
                }}
              />
            ))}
          </div>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
