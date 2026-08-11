import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface SideAccentTitleProps {
  title: string;
  subtitle?: string;
  tag?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const SideAccentTitle: React.FC<SideAccentTitleProps> = ({
  title,
  subtitle = "",
  tag = "",
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const barScale = scaleIn(frame, 0, unit * 2, 0);
  const tagOpacity = fadeIn(frame, unit, unit);
  const titleOpacity = fadeIn(frame, unit * 1.5, unit);
  const titleY = slideUp(frame, unit * 1.5, unit, 30);
  const subtitleOpacity = fadeIn(frame, unit * 2.5, unit);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        fontFamily: font_title,
        overflow: "hidden",
      }}
    >
      {/* Background gradient */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(135deg, ${accent}0A 0%, transparent 50%)`,
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "stretch",
          padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
          gap: spacing.xl,
        }}
      >
        {/* Left accent bar */}
        <div
          style={{
            width: 8,
            backgroundColor: accent,
            borderRadius: 4,
            flexShrink: 0,
            transformOrigin: "top center",
            transform: `scaleY(${barScale})`,
          }}
        />

        {/* Content */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: spacing.md,
          }}
        >
          {tag && (
            <div
              style={{
                color: accent,
                fontSize: typography.label.fontSize,
                fontWeight: 700,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                opacity: tagOpacity,
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 2,
                  backgroundColor: accent,
                  borderRadius: 1,
                }}
              />
              {tag}
            </div>
          )}

          <h1
            style={{
              color: text,
              fontSize: 104,
              fontWeight: 800,
              lineHeight: 1.05,
              margin: 0,
              letterSpacing: "-0.03em",
              maxWidth: 1400,
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h1>

          {subtitle && (
            <p
              style={{
                color: colors.secondary,
                fontSize: typography.card.fontSize,
                fontWeight: 400,
                lineHeight: 1.5,
                margin: 0,
                maxWidth: 900,
                opacity: subtitleOpacity,
                wordBreak: "keep-all",
              }}
            >
              {subtitle}
            </p>
          )}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
