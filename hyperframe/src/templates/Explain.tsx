import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { fadeIn, slideUp } from "../motion/primitives";
import type { ExplainProps } from "../types/scenes";
import { useWordSyncTrigger } from "../motion/wordSync";
import { CaptionOverlay } from "../components/CaptionOverlay";

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

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "row",
        fontFamily: font_title,
        position: "relative",
      }}
    >
      {/* Left 1/3 — title column */}
      <div
        style={{
          width: "33.33%",
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          paddingRight: 48,
          borderRight: `2px solid ${accent}40`,
        }}
      >
        <h2
          style={{
            color: accent,
            fontSize: 52,
            fontWeight: 700,
            textAlign: "right",
            margin: 0,
            lineHeight: 1.3,
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
          }}
        >
          {title}
        </h2>
      </div>

      {/* Right 2/3 — bullets */}
      <div
        style={{
          width: "66.67%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          paddingLeft: 64,
          paddingRight: 80,
          gap: 28,
        }}
      >
        {bullets.map((bullet, i) => {
          const progress = wordSync.progress(i);
          const opacity = wordSync.isWordSync
            ? progress
            : fadeIn(frame, unitFrames + i * unitFrames, unitFrames);
          const y = wordSync.isWordSync
            ? (1 - progress) * 24
            : slideUp(frame, unitFrames + i * unitFrames, unitFrames);

          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 20,
                opacity,
                transform: `translateY(${y}px)`,
              }}
            >
              <span
                style={{
                  color: accent,
                  fontSize: 24,
                  fontWeight: 700,
                  flexShrink: 0,
                  marginTop: 4,
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <p
                style={{
                  color: text,
                  fontSize: 32,
                  fontWeight: 400,
                  margin: 0,
                  lineHeight: 1.6,
                }}
              >
                {bullet}
              </p>
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
