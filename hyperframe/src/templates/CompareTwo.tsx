import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface CompareTwoProps {
  title?: string;
  left_title: string;
  right_title: string;
  left_items: string[];
  right_items: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

const ItemList: React.FC<{
  items: string[];
  color: string;
  frame: number;
  unit: number;
  baseDelay: number;
}> = ({ items, color, frame, unit, baseDelay }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: spacing.md, width: "100%" }}>
    {items.map((item, i) => {
      const start = baseDelay + i * Math.round(unit * 0.6);
      const opacity = fadeIn(frame, start, unit);
      const y = slideUp(frame, start, unit, 20);
      return (
        <div
          key={i}
          style={{
            opacity,
            transform: `translateY(${y}px)`,
            color: text,
            fontSize: typography.body.fontSize,
            fontWeight: 400,
            lineHeight: 1.55,
            padding: `${spacing.md}px ${spacing.lg}px`,
            border: `1.5px solid ${color}35`,
            borderRadius: radius.lg,
            backgroundColor: `${color}10`,
            display: "flex",
            alignItems: "flex-start",
            gap: spacing.md,
            wordBreak: "keep-all",
          }}
        >
          <span style={{ color, fontSize: 20, fontWeight: 700, lineHeight: 2, flexShrink: 0 }}>▸</span>
          <span>{item}</span>
        </div>
      );
    })}
  </div>
);

export const CompareTwo: React.FC<CompareTwoProps> = ({
  title,
  left_title,
  right_title,
  left_items,
  right_items,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const titleY = slideUp(frame, 0, unit);
  const headerOpacity = fadeIn(frame, unit, unit);
  const headerY = slideUp(frame, unit, unit);

  const leftColor = colors.panelLeft;
  const rightColor = colors.panelRight;

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
        gap: spacing.xl,
      }}
    >
      {/* Overall title */}
      {title && (
        <h1
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
        </h1>
      )}

      {/* Two-panel layout */}
      <div
        style={{
          display: "flex",
          width: "100%",
          gap: spacing.lg,
          alignItems: "stretch",
          flex: 1,
          maxHeight: 700,
        }}
      >
        {/* Left panel */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: spacing.lg,
            padding: `${spacing.lg}px`,
            backgroundColor: `${leftColor}0D`,
            border: `1.5px solid ${leftColor}30`,
            borderRadius: radius.xl,
            boxShadow: shadow.card,
            opacity: headerOpacity,
            transform: `translateY(${headerY}px)`,
          }}
        >
          <h2
            style={{
              color: leftColor,
              fontSize: 48,
              fontWeight: 700,
              margin: 0,
              textAlign: "center",
              letterSpacing: "-0.02em",
              paddingBottom: spacing.md,
              borderBottom: `2px solid ${leftColor}30`,
            }}
          >
            {left_title}
          </h2>
          <ItemList items={left_items} color={leftColor} frame={frame} unit={unit} baseDelay={unit * 2} />
        </div>

        {/* Divider */}
        <div
          style={{
            width: 2,
            backgroundColor: `${text}15`,
            borderRadius: 1,
            flexShrink: 0,
          }}
        />

        {/* Right panel */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: spacing.lg,
            padding: `${spacing.lg}px`,
            backgroundColor: `${rightColor}0D`,
            border: `1.5px solid ${rightColor}30`,
            borderRadius: radius.xl,
            boxShadow: shadow.card,
            opacity: headerOpacity,
            transform: `translateY(${headerY}px)`,
          }}
        >
          <h2
            style={{
              color: rightColor,
              fontSize: 48,
              fontWeight: 700,
              margin: 0,
              textAlign: "center",
              letterSpacing: "-0.02em",
              paddingBottom: spacing.md,
              borderBottom: `2px solid ${rightColor}30`,
            }}
          >
            {right_title}
          </h2>
          <ItemList items={right_items} color={rightColor} frame={frame} unit={unit} baseDelay={unit * 2 + Math.round(unit * 0.4)} />
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
