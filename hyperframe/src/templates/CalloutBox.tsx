import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { typography, colors, spacing, radius } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";
import type { CaptionSegment } from "../types/scenes";

interface CalloutBoxProps {
  message: string;
  label?: string;
  note?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const CalloutBox: React.FC<CalloutBoxProps> = ({
  message,
  label,
  note,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const boxScale = scaleIn(frame, 0, unit * 1.5, 0.92);
  const boxOpacity = fadeIn(frame, 0, unit * 1.2);
  const labelOpacity = fadeIn(frame, unit * 0.5, unit);
  const messageOpacity = fadeIn(frame, unit, unit);
  const messageY = slideUp(frame, unit, unit, 20);
  const noteOpacity = fadeIn(frame, unit * 2, unit);

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
      {/* Ambient background glow */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse 70% 50% at 50% 50%, ${accent}08 0%, transparent 70%)`,
        }}
      />

      <div
        style={{
          width: "100%",
          maxWidth: 1400,
          display: "flex",
          flexDirection: "column",
          gap: spacing.xl,
          opacity: boxOpacity,
          transform: `scale(${boxScale})`,
        }}
      >
        {label && (
          <div
            style={{
              display: "inline-flex",
              alignSelf: "flex-start",
              padding: `8px 24px`,
              backgroundColor: `${accent}20`,
              border: `1.5px solid ${accent}60`,
              borderRadius: radius.full,
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              opacity: labelOpacity,
            }}
          >
            {label}
          </div>
        )}

        {/* Main callout box */}
        <div
          style={{
            backgroundColor: colors.surface,
            border: `2px solid ${accent}50`,
            borderLeft: `6px solid ${accent}`,
            borderRadius: radius.lg,
            padding: `${spacing.xxl}px ${spacing.xl}px`,
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* Inner glow */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: 1,
              backgroundColor: `${accent}40`,
            }}
          />

          <p
            style={{
              color: text,
              fontSize: message.length > 80 ? typography.card.fontSize : typography.section.fontSize,
              fontWeight: 600,
              lineHeight: 1.5,
              margin: 0,
              opacity: messageOpacity,
              transform: `translateY(${messageY}px)`,
              wordBreak: "keep-all",
            }}
          >
            {message}
          </p>
        </div>

        {note && (
          <p
            style={{
              color: colors.secondary,
              fontSize: typography.body.fontSize,
              fontWeight: 400,
              lineHeight: 1.5,
              margin: 0,
              opacity: noteOpacity,
              paddingLeft: spacing.md,
              wordBreak: "keep-all",
            }}
          >
            {note}
          </p>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
