import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface TwoColumnTextProps {
  leftTitle?: string;
  leftBody: string;
  rightTitle?: string;
  rightBody: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const TwoColumnText: React.FC<TwoColumnTextProps> = ({
  leftTitle,
  leftBody,
  rightTitle,
  rightBody,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const leftOpacity = fadeIn(frame, 0, unit * 1.2);
  const leftY = slideUp(frame, 0, unit * 1.2, 30);
  const rightOpacity = fadeIn(frame, unit * 0.8, unit * 1.2);
  const rightY = slideUp(frame, unit * 0.8, unit * 1.2, 30);

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
          flexDirection: "row",
          gap: 0,
          width: "100%",
          alignItems: "stretch",
        }}
      >
        {/* Left column */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: spacing.md,
            paddingRight: spacing.xl,
            opacity: leftOpacity,
            transform: `translateY(${leftY}px)`,
          }}
        >
          {leftTitle && (
            <h3
              style={{
                color: accent,
                fontSize: typography.section.fontSize,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                margin: 0,
                wordBreak: "keep-all",
              }}
            >
              {leftTitle}
            </h3>
          )}
          <p
            style={{
              color: text,
              fontSize: typography.card.fontSize,
              fontWeight: 400,
              lineHeight: 1.65,
              margin: 0,
              wordBreak: "keep-all",
            }}
          >
            {leftBody}
          </p>
        </div>

        {/* Divider */}
        <div
          style={{
            width: 2,
            backgroundColor: `${accent}30`,
            flexShrink: 0,
            alignSelf: "stretch",
            marginTop: 8,
            marginBottom: 8,
          }}
        />

        {/* Right column */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: spacing.md,
            paddingLeft: spacing.xl,
            opacity: rightOpacity,
            transform: `translateY(${rightY}px)`,
          }}
        >
          {rightTitle && (
            <h3
              style={{
                color: colors.panelRight,
                fontSize: typography.section.fontSize,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                margin: 0,
                wordBreak: "keep-all",
              }}
            >
              {rightTitle}
            </h3>
          )}
          <p
            style={{
              color: text,
              fontSize: typography.card.fontSize,
              fontWeight: 400,
              lineHeight: 1.65,
              margin: 0,
              wordBreak: "keep-all",
            }}
          >
            {rightBody}
          </p>
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
