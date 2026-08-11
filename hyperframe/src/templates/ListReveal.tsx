import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { fadeIn, slideUp } from "../motion/primitives";
import type { ListRevealProps } from "../types/scenes";
import { useWordSyncTrigger } from "../motion/wordSync";
import { CaptionOverlay } from "../components/CaptionOverlay";

export const ListReveal: React.FC<ListRevealProps> = ({
  title,
  items,
  durationInFrames,
  motionAnchors,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unitFrames = Math.round((fps * 300) / 1000);

  const titleOpacity = fadeIn(frame, 0, unitFrames);
  const titleY = slideUp(frame, 0, unitFrames);

  const wordSync = useWordSyncTrigger(motionAnchors, unitFrames, items.length);

  // active card: word-sync 모드면 마지막으로 visible 된 카드, 아니면 시간 기반
  const activeIndex = wordSync.isWordSync
    ? Math.max(-1, ...items.map((_, i) => (wordSync.isVisible(i) ? i : -1)))
    : Math.min(Math.floor((frame - unitFrames) / unitFrames), items.length - 1);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        display: "flex",
        flexDirection: "column",
        padding: "72px 120px",
        fontFamily: font_title,
      }}
    >
      <h2
        style={{
          color: text,
          fontSize: 48,
          fontWeight: 700,
          margin: "0 0 48px 0",
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        {title}
      </h2>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 20,
          flex: 1,
        }}
      >
        {items.map((item, i) => {
          const progress = wordSync.progress(i);
          const isVisible = wordSync.isVisible(i);
          const delay = unitFrames + i * unitFrames;

          const opacity = wordSync.isWordSync
            ? progress
            : frame > delay
              ? 1
              : fadeIn(frame, delay, unitFrames);

          const y = wordSync.isWordSync
            ? (1 - progress) * 24
            : frame > delay
              ? 0
              : slideUp(frame, delay, unitFrames);

          const isActive = i === activeIndex && (wordSync.isWordSync ? isVisible : frame > unitFrames);
          const cardScale = isActive ? 1.05 : 1.0;

          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 24,
                opacity,
                transform: `translateY(${y}px) scale(${cardScale})`,
                backgroundColor: isActive ? `${accent}18` : `${text}0a`,
                border: `1px solid ${isActive ? accent : text + "20"}`,
                borderRadius: 12,
                padding: "20px 28px",
              }}
            >
              <span
                style={{
                  color: accent,
                  fontSize: 22,
                  fontWeight: 700,
                  minWidth: 36,
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <p
                style={{
                  color: isActive ? text : text + "cc",
                  fontSize: 28,
                  fontWeight: isActive ? 500 : 400,
                  margin: 0,
                  lineHeight: 1.5,
                }}
              >
                {item}
              </p>
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
