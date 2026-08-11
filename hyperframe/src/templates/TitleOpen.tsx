import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, radius, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import type { TitleOpenProps } from "../types/scenes";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";

export const TitleOpen: React.FC<TitleOpenProps> = ({
  title,
  subtitle = "",
  category = "",
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unitFrames = Math.round((fps * 300) / 1000);

  const bgOpacity = fadeIn(frame, 0, unitFrames * 2);
  const categoryOpacity = fadeIn(frame, Math.round(unitFrames * 0.5), unitFrames);
  const categoryY = slideUp(frame, Math.round(unitFrames * 0.5), unitFrames, 20);
  const titleOpacity = fadeIn(frame, unitFrames, unitFrames);
  const titleY = slideUp(frame, unitFrames, unitFrames);
  const titleScale = scaleIn(frame, unitFrames, unitFrames, 0.92);
  const subtitleOpacity = fadeIn(frame, unitFrames * 2, unitFrames);
  const lineOpacity = fadeIn(frame, Math.round(unitFrames * 1.5), unitFrames);

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
      {/* Radial gradient background — large, soft */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse 90% 70% at 50% 50%, ${accent}1A 0%, transparent 65%)`,
          opacity: bgOpacity,
        }}
      />

      {/* Bottom gradient atmosphere */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 300,
          background: `linear-gradient(to top, ${accent}0A 0%, transparent 100%)`,
          opacity: bgOpacity,
        }}
      />

      {/* Content container */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.lg,
          padding: `0 ${SAFE_AREA.left}px`,
          maxWidth: 1400,
        }}
      >
        {/* Category label */}
        {category && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.15em",
              opacity: categoryOpacity,
              transform: `translateY(${categoryY}px)`,
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div style={{ width: 32, height: 2, backgroundColor: accent, opacity: 0.6 }} />
            {category}
            <div style={{ width: 32, height: 2, backgroundColor: accent, opacity: 0.6 }} />
          </div>
        )}

        {/* Hero title */}
        <h1
          style={{
            color: text,
            fontSize: typography.hero.fontSize,
            fontWeight: typography.hero.fontWeight,
            textAlign: "center",
            margin: 0,
            lineHeight: typography.hero.lineHeight,
            opacity: titleOpacity,
            transform: `translateY(${titleY}px) scale(${titleScale})`,
            letterSpacing: typography.hero.letterSpacing,
            wordBreak: "keep-all",
          }}
        >
          {title}
        </h1>

        {/* Divider line */}
        <div
          style={{
            width: 80,
            height: 3,
            backgroundColor: accent,
            borderRadius: 2,
            opacity: lineOpacity * 0.5,
          }}
        />

        {/* Subtitle */}
        {subtitle && (
          <p
            style={{
              color: accent,
              fontSize: 38,
              fontWeight: 500,
              marginTop: 0,
              opacity: subtitleOpacity,
              letterSpacing: "0.02em",
              textAlign: "center",
              padding: `14px 36px`,
              borderRadius: radius.md,
              border: `1.5px solid ${accent}35`,
              backgroundColor: `${accent}0D`,
              lineHeight: 1.5,
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
