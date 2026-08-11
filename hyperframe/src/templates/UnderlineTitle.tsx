import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill, interpolate } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface UnderlineTitleProps {
  title: string;
  subtitle?: string;
  label?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const UnderlineTitle: React.FC<UnderlineTitleProps> = ({
  title,
  subtitle = "",
  label = "",
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const labelOpacity = fadeIn(frame, 0, unit);
  const titleOpacity = fadeIn(frame, unit, unit);
  const titleY = slideUp(frame, unit, unit, 40);

  // Underline expands from left to right
  const underlineWidth = interpolate(frame, [unit * 2, unit * 4], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const subtitleOpacity = fadeIn(frame, unit * 3, unit);

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
      {/* Subtle corner accent */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: 240,
          height: 240,
          background: `radial-gradient(circle at top left, ${accent}18 0%, transparent 70%)`,
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.lg,
          padding: `0 ${SAFE_AREA.left}px`,
          maxWidth: 1400,
          width: "100%",
          textAlign: "center",
        }}
      >
        {/* Label */}
        {label && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              opacity: labelOpacity,
            }}
          >
            {label}
          </div>
        )}

        {/* Title with animated underline */}
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
          <h1
            style={{
              color: text,
              fontSize: typography.hero.fontSize,
              fontWeight: typography.hero.fontWeight,
              lineHeight: typography.hero.lineHeight,
              letterSpacing: typography.hero.letterSpacing,
              margin: 0,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h1>

          {/* Animated underline bar */}
          <div
            style={{
              height: 6,
              width: "80%",
              backgroundColor: colors.border,
              borderRadius: 3,
              overflow: "hidden",
              position: "relative",
            }}
          >
            <div
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                bottom: 0,
                width: `${underlineWidth}%`,
                background: `linear-gradient(to right, ${accent}, ${accent}99)`,
                borderRadius: 3,
              }}
            />
          </div>
        </div>

        {/* Subtitle */}
        {subtitle && (
          <p
            style={{
              color: colors.secondary,
              fontSize: typography.body.fontSize,
              fontWeight: 400,
              lineHeight: typography.body.lineHeight,
              margin: 0,
              opacity: subtitleOpacity,
              maxWidth: 900,
              wordBreak: "keep-all",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
