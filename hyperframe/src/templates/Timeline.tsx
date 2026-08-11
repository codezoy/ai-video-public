import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill, interpolate } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp, EASE_OUT_EXPO } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface TimelineProps {
  title: string;
  category?: string;
  events: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const Timeline: React.FC<TimelineProps> = ({
  title,
  category,
  events,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const categoryOpacity = fadeIn(frame, 0, unit);
  const titleOpacity = fadeIn(frame, Math.round(unit * 0.4), unit);
  const titleY = slideUp(frame, Math.round(unit * 0.4), unit);

  const count = events.length;
  const lineWidth = interpolate(
    frame,
    [unit, unit + count * unit],
    [0, 90],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT_EXPO }
  );

  const dotSize = count <= 4 ? 52 : 44;
  const labelFontSize = count <= 3 ? 32 : count <= 4 ? 28 : 24;
  const subFontSize = count <= 3 ? 26 : 22;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: font_title,
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
        gap: spacing.lg,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {category && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              opacity: categoryOpacity,
            }}
          >
            {category}
          </div>
        )}
        <h2
          style={{
            color: text,
            fontSize: typography.section.fontSize,
            fontWeight: typography.section.fontWeight,
            margin: 0,
            textAlign: "center",
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            letterSpacing: typography.section.letterSpacing,
            wordBreak: "keep-all",
          }}
        >
          {title}
        </h2>
      </div>

      {/* Timeline track */}
      <div
        style={{
          position: "relative",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
          width: "100%",
          maxWidth: 1500,
        }}
      >
        {/* Growing horizontal line */}
        <div
          style={{
            position: "absolute",
            top: Math.floor(dotSize / 2) - 1,
            left: `${Math.floor(100 / (count * 2))}%`,
            height: 3,
            width: `${lineWidth}%`,
            backgroundColor: accent,
            borderRadius: radius.sm,
            transformOrigin: "left center",
            opacity: 0.6,
          }}
        />

        {/* Events */}
        {events.map((evt, i) => {
          const evtStart = unit + i * unit;
          const evtOpacity = fadeIn(frame, evtStart, unit);
          const evtY = slideUp(frame, evtStart, unit, 28);

          const lines = evt.split("\n");
          const mainLabel = lines[0];
          const subLabel = lines[1] ?? "";

          return (
            <div
              key={i}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: spacing.md,
                opacity: evtOpacity,
                transform: `translateY(${evtY}px)`,
              }}
            >
              {/* Dot */}
              <div
                style={{
                  width: dotSize,
                  height: dotSize,
                  borderRadius: radius.full,
                  backgroundColor: accent,
                  border: `4px solid ${bg}`,
                  boxShadow: `${shadow.glow(accent, "40")}, 0 0 0 2px ${accent}60`,
                  zIndex: 1,
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <span
                  style={{
                    color: bg,
                    fontSize: 20,
                    fontWeight: 800,
                  }}
                >
                  {i + 1}
                </span>
              </div>

              {/* Label card */}
              <div
                style={{
                  color: text,
                  textAlign: "center",
                  lineHeight: 1.4,
                  padding: `${spacing.md}px ${spacing.md}px`,
                  border: `1.5px solid ${accent}30`,
                  borderRadius: radius.lg,
                  backgroundColor: colors.surface,
                  boxShadow: shadow.card,
                  maxWidth: 300,
                  display: "flex",
                  flexDirection: "column",
                  gap: spacing.xs,
                }}
              >
                <span style={{ fontSize: labelFontSize, fontWeight: 700 }}>{mainLabel}</span>
                {subLabel && (
                  <span style={{ fontSize: subFontSize, fontWeight: 400, color: `${text}80` }}>
                    {subLabel}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
