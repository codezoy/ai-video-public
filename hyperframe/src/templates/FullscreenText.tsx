import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface FullscreenTextProps {
  headline: string;
  subtext?: string;
  label?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const FullscreenText: React.FC<FullscreenTextProps> = ({
  headline,
  subtext,
  label,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const labelOpacity = fadeIn(frame, 0, unit);
  const headlineOpacity = fadeIn(frame, unit * 0.5, unit * 1.5);
  const headlineY = slideUp(frame, unit * 0.5, unit * 1.5, 60);
  const subtextOpacity = fadeIn(frame, unit * 2, unit);

  const headlineFontSize = headline.length > 30 ? 96 : headline.length > 15 ? 120 : 152;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "center",
        fontFamily: font_title,
        overflow: "hidden",
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
      }}
    >
      {/* Subtle corner accent */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          right: 0,
          width: 400,
          height: 400,
          background: `radial-gradient(circle at 100% 100%, ${accent}0D 0%, transparent 70%)`,
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: spacing.lg,
          maxWidth: 1600,
        }}
      >
        {label && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              opacity: labelOpacity,
            }}
          >
            {label}
          </div>
        )}

        <h1
          style={{
            color: text,
            fontSize: headlineFontSize,
            fontWeight: 900,
            lineHeight: 1.0,
            margin: 0,
            letterSpacing: "-0.04em",
            opacity: headlineOpacity,
            transform: `translateY(${headlineY}px)`,
            wordBreak: "keep-all",
          }}
        >
          {headline}
        </h1>

        {subtext && (
          <p
            style={{
              color: colors.secondary,
              fontSize: typography.card.fontSize,
              fontWeight: 400,
              lineHeight: 1.55,
              margin: 0,
              maxWidth: 800,
              opacity: subtextOpacity,
              wordBreak: "keep-all",
              borderLeft: `3px solid ${accent}60`,
              paddingLeft: spacing.lg,
            }}
          >
            {subtext}
          </p>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
