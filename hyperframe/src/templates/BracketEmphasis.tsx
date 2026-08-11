import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill, interpolate, Easing } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface BracketEmphasisProps {
  keyword: string;
  context?: string;
  detail?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const BracketEmphasis: React.FC<BracketEmphasisProps> = ({
  keyword,
  context,
  detail,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const contextOpacity = fadeIn(frame, 0, unit);
  const bracketLeft = interpolate(frame, [unit * 0.5, unit * 1.5], [-120, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.2)),
  });
  const bracketRight = interpolate(frame, [unit * 0.5, unit * 1.5], [120, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.2)),
  });
  const keywordOpacity = fadeIn(frame, unit * 0.5, unit);
  const keywordY = slideUp(frame, unit * 0.5, unit, 30);
  const detailOpacity = fadeIn(frame, unit * 2, unit);

  const keywordFontSize = keyword.length > 20 ? 96 : keyword.length > 10 ? 120 : 148;

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
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.xl,
          width: "100%",
          maxWidth: 1600,
        }}
      >
        {context && (
          <p
            style={{
              color: colors.secondary,
              fontSize: typography.card.fontSize,
              fontWeight: 400,
              letterSpacing: "0.02em",
              margin: 0,
              textAlign: "center",
              opacity: contextOpacity,
              wordBreak: "keep-all",
            }}
          >
            {context}
          </p>
        )}

        {/* Bracket + keyword row */}
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.lg,
          }}
        >
          {/* Left bracket */}
          <div
            style={{
              transform: `translateX(${bracketLeft}px)`,
              display: "flex",
              flexDirection: "column",
              gap: 0,
            }}
          >
            <div style={{ width: 40, height: 8, backgroundColor: accent, borderRadius: 2 }} />
            <div style={{ width: 8, height: keywordFontSize * 1.2, backgroundColor: accent, borderRadius: 2 }} />
            <div style={{ width: 40, height: 8, backgroundColor: accent, borderRadius: 2 }} />
          </div>

          {/* Keyword */}
          <h1
            style={{
              color: accent,
              fontSize: keywordFontSize,
              fontWeight: 900,
              letterSpacing: "-0.03em",
              margin: 0,
              textAlign: "center",
              opacity: keywordOpacity,
              transform: `translateY(${keywordY}px)`,
              wordBreak: "keep-all",
            }}
          >
            {keyword}
          </h1>

          {/* Right bracket */}
          <div
            style={{
              transform: `translateX(${bracketRight}px)`,
              display: "flex",
              flexDirection: "column",
              gap: 0,
              alignItems: "flex-end",
            }}
          >
            <div style={{ width: 40, height: 8, backgroundColor: accent, borderRadius: 2 }} />
            <div style={{ width: 8, height: keywordFontSize * 1.2, backgroundColor: accent, borderRadius: 2, alignSelf: "flex-end" }} />
            <div style={{ width: 40, height: 8, backgroundColor: accent, borderRadius: 2 }} />
          </div>
        </div>

        {detail && (
          <p
            style={{
              color: text,
              fontSize: typography.body.fontSize,
              fontWeight: 400,
              lineHeight: 1.6,
              margin: 0,
              textAlign: "center",
              maxWidth: 900,
              opacity: detailOpacity,
              wordBreak: "keep-all",
            }}
          >
            {detail}
          </p>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
