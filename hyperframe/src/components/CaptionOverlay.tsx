import React from "react";
import type { CaptionSegment } from "../types/scenes";
import type { CaptionStyleConfig } from "../theme/captionStyle";
import { DEFAULT_CAPTION_STYLE } from "../theme/captionStyle";
import { useCaptionSync } from "../motion/captionSync";

interface CaptionOverlayProps {
  captionSegments?: CaptionSegment[] | null;
  style?: Partial<CaptionStyleConfig>;
}

function resolvePosition(config: CaptionStyleConfig): React.CSSProperties {
  const base: React.CSSProperties = {
    position: "absolute",
    left: "50%",
    transform: "translateX(-50%)",
    width: "100%",
    maxWidth: config.maxWidth,
    textAlign: config.align,
    pointerEvents: "none",
    zIndex: 1000,
  };

  if (config.position === "bottom") {
    return { ...base, bottom: config.safeAreaBottom };
  }
  if (config.position === "top") {
    return { ...base, top: config.safeAreaBottom };
  }
  return { ...base, top: "50%", transform: "translate(-50%, -50%)" };
}

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  captionSegments,
  style: styleOverride,
}) => {
  const config: CaptionStyleConfig = { ...DEFAULT_CAPTION_STYLE, ...styleOverride };
  const { currentCaption, isActive, progress, currentWordIdx } =
    useCaptionSync(captionSegments, config.fadeMs);

  if (!isActive || !currentCaption) return null;

  const activeSegment = captionSegments?.find((seg) => seg.text === currentCaption);
  const hasWordTimestamps =
    activeSegment?.word_timestamps && activeSegment.word_timestamps.length > 0;

  const bgRgb = hexToRgb(config.backgroundColor);
  const bgColor = bgRgb
    ? `rgba(${bgRgb.r}, ${bgRgb.g}, ${bgRgb.b}, ${config.backgroundOpacity})`
    : config.backgroundColor;

  const renderContent = () => {
    const baseTextStyle: React.CSSProperties = {
      fontSize: config.fontSize,
      fontFamily: config.fontFamily,
      fontWeight: config.fontWeight,
      lineHeight: 1.5,
      letterSpacing: "0.01em",
    };

    if (!hasWordTimestamps || !activeSegment?.word_timestamps) {
      return (
        <span style={{ ...baseTextStyle, color: config.color }}>
          {currentCaption}
        </span>
      );
    }

    return (
      <span style={baseTextStyle}>
        {activeSegment.word_timestamps.map((wt, idx) => (
          <span
            key={idx}
            style={{
              color: idx === currentWordIdx ? config.highlightColor : config.color,
              fontWeight: idx === currentWordIdx ? 700 : config.fontWeight,
              transition: "color 80ms ease, font-weight 80ms ease",
            }}
          >
            {wt.word}
            {idx < activeSegment.word_timestamps!.length - 1 ? " " : ""}
          </span>
        ))}
      </span>
    );
  };

  return (
    <div style={{ ...resolvePosition(config), opacity: progress }}>
      <div
        style={{
          display: "inline-block",
          backgroundColor: bgColor,
          borderRadius: config.borderRadius,
          padding: `${config.paddingY}px ${config.paddingX}px`,
          maxWidth: "100%",
        }}
      >
        {renderContent()}
      </div>
    </div>
  );
};

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return m
    ? { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) }
    : null;
}
