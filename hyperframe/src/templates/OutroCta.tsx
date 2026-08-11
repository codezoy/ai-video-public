import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { fadeIn, slideUp, pulse } from "../motion/primitives";
import type { OutroCtaProps } from "../types/scenes";

export const OutroCta: React.FC<OutroCtaProps> = ({
  nextVideos = [],
  channelName = "",
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unitFrames = Math.round((fps * 300) / 1000);
  const pulsePeriod = fps * 2;

  const headerOpacity = fadeIn(frame, 0, unitFrames);
  const headerY = slideUp(frame, 0, unitFrames);

  const channelScale = pulse(frame, pulsePeriod, 0.04);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 80px",
        fontFamily: font_title,
        gap: 56,
      }}
    >
      {/* Header */}
      <h2
        style={{
          color: text,
          fontSize: 52,
          fontWeight: 700,
          margin: 0,
          textAlign: "center",
          opacity: headerOpacity,
          transform: `translateY(${headerY}px)`,
        }}
      >
        다음 영상
      </h2>

      {/* Next video cards (max 2) */}
      <div
        style={{
          display: "flex",
          gap: 40,
          width: "100%",
          justifyContent: "center",
        }}
      >
        {nextVideos.slice(0, 2).map((video, i) => {
          const delay = unitFrames + i * unitFrames;
          const opacity = fadeIn(frame, delay, unitFrames);
          const y = slideUp(frame, delay, unitFrames);
          return (
            <div
              key={i}
              style={{
                flex: 1,
                maxWidth: 480,
                backgroundColor: `${text}0d`,
                border: `1px solid ${accent}50`,
                borderRadius: 16,
                padding: "32px 36px",
                opacity,
                transform: `translateY(${y}px)`,
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  backgroundColor: accent,
                  marginBottom: 20,
                }}
              />
              <p
                style={{
                  color: text,
                  fontSize: 26,
                  fontWeight: 500,
                  margin: 0,
                  lineHeight: 1.5,
                }}
              >
                {video}
              </p>
            </div>
          );
        })}
      </div>

      {/* Channel signature — pulse loop */}
      {channelName && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
            opacity: frame > unitFrames * 3 ? 1 : fadeIn(frame, unitFrames * 3, unitFrames),
            transform: `scale(${channelScale})`,
          }}
        >
          <div
            style={{
              width: 2,
              height: 48,
              backgroundColor: accent,
            }}
          />
          <p
            style={{
              color: accent,
              fontSize: 32,
              fontWeight: 700,
              margin: 0,
              letterSpacing: "0.08em",
            }}
          >
            {channelName}
          </p>
          <p
            style={{
              color: text + "80",
              fontSize: 24,
              margin: 0,
              letterSpacing: "0.04em",
            }}
          >
            구독 · 좋아요
          </p>
        </div>
      )}
    </AbsoluteFill>
  );
};
