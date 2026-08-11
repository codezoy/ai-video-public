import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { fadeIn, slideUp } from "../motion/primitives";
import type { QuoteProps } from "../types/scenes";
import { CaptionOverlay } from "../components/CaptionOverlay";

export const Quote: React.FC<QuoteProps> = ({
  quote,
  source = "",
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unitFrames = Math.round((fps * 300) / 1000);
  const sourceDelayFrames = Math.round(fps * 1);

  const glyphOpacity = fadeIn(frame, 0, unitFrames);

  const quoteOpacity = fadeIn(frame, unitFrames, unitFrames);

  const sourceOpacity = fadeIn(frame, unitFrames * 2 + sourceDelayFrames, unitFrames);
  const sourceY = slideUp(frame, unitFrames * 2 + sourceDelayFrames, unitFrames);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 160px",
        fontFamily: font_title,
      }}
    >
      {/* Quote mark graphic */}
      <div
        style={{
          fontSize: 160,
          color: accent,
          lineHeight: 0.8,
          opacity: glyphOpacity,
          alignSelf: "flex-start",
          marginLeft: -16,
          marginBottom: 16,
        }}
      >
        "
      </div>

      {/* Quote text */}
      <p
        style={{
          color: text,
          fontSize: 44,
          fontWeight: 400,
          lineHeight: 1.7,
          margin: 0,
          textAlign: "center",
          minHeight: 220,
          opacity: quoteOpacity,
        }}
      >
        {quote}
      </p>

      {/* Source */}
      {source && (
        <p
          style={{
            color: accent,
            fontSize: 28,
            fontWeight: 500,
            marginTop: 40,
            opacity: sourceOpacity,
            transform: `translateY(${sourceY}px)`,
            letterSpacing: "0.06em",
          }}
        >
          — {source}
        </p>
      )}
      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
