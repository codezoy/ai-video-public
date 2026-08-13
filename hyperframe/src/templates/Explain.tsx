import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import type { ExplainProps } from "../types/scenes";
import { useWordSyncTrigger } from "../motion/wordSync";
import { CaptionOverlay } from "../components/CaptionOverlay";
import { SAFE_AREA } from "../lib/safearea";

export const Explain: React.FC<ExplainProps> = ({
  title,
  bullets,
  durationInFrames,
  motionAnchors,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unitFrames = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unitFrames);
  const titleY = slideUp(frame, 0, unitFrames);

  const wordSync = useWordSyncTrigger(motionAnchors, unitFrames, bullets.length);
  const bulletCount = Math.max(1, bullets.length);
  const columns = bulletCount <= 3 ? bulletCount : bulletCount <= 6 ? 3 : 4;
  const compact = bulletCount >= 6;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        fontFamily: font_title,
        position: "relative",
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom + 142}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "grid",
          gridTemplateRows: "auto minmax(0, 1fr)",
          rowGap: spacing.xl,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            alignItems: "end",
            columnGap: spacing.xl,
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
          }}
        >
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              textAlign: "left",
              margin: 0,
              lineHeight: typography.section.lineHeight,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: typography.label.fontWeight,
              letterSpacing: typography.label.letterSpacing,
              textTransform: "uppercase",
              paddingBottom: 8,
              whiteSpace: "nowrap",
            }}
          >
            EXPLAIN
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
            gap: compact ? spacing.md : spacing.lg,
            alignSelf: "center",
            width: "100%",
          }}
        >
          {bullets.map((bullet, i) => {
            const progress = wordSync.progress(i);
            const delay = unitFrames + i * Math.round(unitFrames * 0.55);
            const opacity = wordSync.isWordSync ? progress : fadeIn(frame, delay, unitFrames);
            const y = wordSync.isWordSync
              ? (1 - progress) * 20
              : slideUp(frame, delay, unitFrames, 20);

            return (
              <div
                key={i}
                style={{
                  minHeight: compact ? 150 : 190,
                  display: "grid",
                  gridTemplateRows: "auto 1fr",
                  rowGap: spacing.sm,
                  padding: compact ? `${spacing.md}px` : `${spacing.lg}px`,
                  borderRadius: radius.lg,
                  border: `1.5px solid ${accent}35`,
                  backgroundColor: colors.surface,
                  boxShadow: shadow.card,
                  opacity,
                  transform: `translateY(${y}px)`,
                }}
              >
                <div
                  style={{
                    color: accent,
                    fontSize: compact ? 22 : 26,
                    fontWeight: 800,
                    lineHeight: 1,
                  }}
                >
                  {String(i + 1).padStart(2, "0")}
                </div>
                <p
                  style={{
                    color: text,
                    fontSize: compact ? 26 : 32,
                    fontWeight: 500,
                    margin: 0,
                    lineHeight: 1.42,
                    wordBreak: "keep-all",
                    alignSelf: "center",
                  }}
                >
                  {bullet}
                </p>
              </div>
            );
          })}
          {bullets.length === 0 && (
            <div
              style={{
                color: `${text}99`,
                fontSize: 30,
                padding: spacing.lg,
                border: `1.5px solid ${accent}30`,
                borderRadius: radius.lg,
                backgroundColor: colors.surface,
              }}
            >
              {title}
            </div>
          )}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
