import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface KeywordCardsProps {
  title?: string;
  keywords: string[];
  icons?: string[];
  descriptions?: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

const DEFAULT_ICONS = ["💡", "🔥", "⚡", "🎯", "🚀", "💎", "🧠", "✨"];

export const KeywordCards: React.FC<KeywordCardsProps> = ({
  title,
  keywords,
  icons,
  descriptions,
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unit);
  const titleY = slideUp(frame, 0, unit);

  const count = keywords.length;
  const isGrid = count >= 4;
  const cardMinW = count <= 3 ? 380 : count <= 4 ? 340 : 300;
  const cardMinH = count <= 3 ? 280 : count <= 4 ? 240 : 200;
  const iconSize = count <= 3 ? 80 : 64;
  const labelSize = count <= 3 ? typography.card.fontSize : 36;
  const descSize = count <= 3 ? 28 : 24;

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
      {/* Title */}
      {title && (
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
      )}

      {/* Keyword cards grid */}
      <div
        style={{
          display: "flex",
          flexWrap: isGrid ? "wrap" : "nowrap",
          gap: spacing.lg,
          justifyContent: "center",
          alignItems: "stretch",
          width: "100%",
          maxWidth: count <= 3 ? 1400 : 1600,
        }}
      >
        {keywords.map((kw, i) => {
          const cardStart = (title ? unit : 0) + i * Math.round(unit * 0.5);
          const cardOpacity = fadeIn(frame, cardStart, unit);
          const cardScale = scaleIn(frame, cardStart, unit, 0.88);
          const cardY = slideUp(frame, cardStart, unit, 36);
          const iconEmoji = icons?.[i] ?? DEFAULT_ICONS[i % DEFAULT_ICONS.length];
          const desc = descriptions?.[i] ?? "";
          const cardColor = colors.cardPalette[i % colors.cardPalette.length];

          return (
            <div
              key={i}
              style={{
                opacity: cardOpacity,
                transform: `scale(${cardScale}) translateY(${cardY}px)`,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: spacing.md,
                padding: `${spacing.xl}px ${spacing.lg}px`,
                border: `1.5px solid ${cardColor}30`,
                borderRadius: radius.xl,
                backgroundColor: colors.surface,
                boxShadow: `${shadow.card}, ${shadow.glow(cardColor, "15")}`,
                minWidth: cardMinW,
                minHeight: cardMinH,
                flex: "1 1 auto",
                maxWidth: count <= 3 ? 440 : 380,
              }}
            >
              {/* Icon */}
              <div
                style={{
                  fontSize: iconSize,
                  lineHeight: 1,
                  filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.4))",
                }}
              >
                {iconEmoji}
              </div>

              {/* Keyword label */}
              <div
                style={{
                  color: text,
                  fontSize: labelSize,
                  fontWeight: 700,
                  textAlign: "center",
                  lineHeight: 1.25,
                  letterSpacing: "-0.01em",
                }}
              >
                {kw}
              </div>

              {/* Description */}
              {desc && (
                <div
                  style={{
                    color: `${text}80`,
                    fontSize: descSize,
                    fontWeight: 400,
                    textAlign: "center",
                    lineHeight: 1.4,
                    letterSpacing: "0",
                  }}
                >
                  {desc}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
