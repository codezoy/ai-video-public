import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, typography, spacing, radius, shadow, fonts } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { SAFE_AREA } from "../lib/safearea";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";

type LineStatus = "command" | "output" | "success" | "warning" | "error";

interface TerminalLine {
  text: string;
  type: LineStatus;
}

interface TerminalProps {
  title: string;
  prompt?: string;
  lines: TerminalLine[];
  typing?: boolean;
  captionSegments?: CaptionSegment[] | null;
  durationInFrames?: number;
}

const STATUS_CONFIG: Record<LineStatus, { color: string; prefix: string }> = {
  command: { color: "#C9ADA7", prefix: "" },
  output:  { color: "#8B9DC8", prefix: "" },
  success: { color: "#6FCF97", prefix: "✓ " },
  warning: { color: "#F2C94C", prefix: "⚠ " },
  error:   { color: "#EB5757", prefix: "✗ " },
};

export const TerminalComposition: React.FC<TerminalProps> = ({
  title,
  prompt = "$",
  lines,
  typing = true,
  captionSegments,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const UNIT = Math.round((fps * 300) / 1000);
  const headerIn = 0;
  const termIn = UNIT;

  const getLineOpacity = (idx: number) => {
    const start = termIn + (idx * UNIT * 0.6);
    return fadeIn(frame, start, UNIT);
  };

  const getTypedText = (line: TerminalLine, idx: number): string => {
    if (!typing || line.type !== "command") return line.text;
    const start = termIn + (idx * UNIT * 0.6);
    const elapsed = Math.max(0, frame - start);
    const charsVisible = Math.floor((elapsed / (fps * 0.5)) * line.text.length);
    return line.text.slice(0, Math.min(charsVisible, line.text.length));
  };

  const showCursor = (line: TerminalLine, idx: number): boolean => {
    if (!typing || line.type !== "command") return false;
    const start = termIn + (idx * UNIT * 0.6);
    const elapsed = Math.max(0, frame - start);
    const charsVisible = Math.floor((elapsed / (fps * 0.5)) * line.text.length);
    return charsVisible < line.text.length;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 800px 500px at 30% 50%, ${colors.surface}88 0%, transparent 70%)`,
        }}
      />

      <div
        style={{
          position: "absolute",
          top: SAFE_AREA.top,
          left: SAFE_AREA.left,
          width: SAFE_AREA.safeWidth,
          height: SAFE_AREA.safeHeight,
          display: "flex",
          flexDirection: "column",
          gap: spacing.lg,
        }}
      >
        {/* header */}
        <div
          style={{
            opacity: fadeIn(frame, headerIn, UNIT),
            transform: `translateY(${slideUp(frame, headerIn, UNIT)}px)`,
          }}
        >
          <div
            style={{
              fontFamily: fonts.body,
              fontSize: typography.label.fontSize,
              fontWeight: typography.label.fontWeight,
              letterSpacing: "0.12em",
              color: colors.secondary,
              textTransform: "uppercase",
              marginBottom: spacing.xs,
            }}
          >
            Terminal
          </div>
          <div
            style={{
              fontFamily: fonts.title,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              letterSpacing: typography.section.letterSpacing,
              color: colors.text,
              lineHeight: 1.1,
            }}
          >
            {title}
          </div>
        </div>

        {/* terminal panel */}
        <div
          style={{
            flex: 1,
            backgroundColor: "#0A0A10",
            borderRadius: radius.lg,
            border: `1px solid ${colors.border}`,
            boxShadow: shadow.elevated,
            overflow: "hidden",
            opacity: fadeIn(frame, termIn - UNIT / 2, UNIT),
          }}
        >
          {/* title bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: spacing.sm,
              padding: `${spacing.sm}px ${spacing.md}px`,
              borderBottom: `1px solid ${colors.border}`,
              backgroundColor: `${colors.surface}99`,
            }}
          >
            {["#FF5F57", "#FEBC2E", "#28C840"].map((c, i) => (
              <div
                key={i}
                style={{ width: 14, height: 14, borderRadius: "50%", backgroundColor: c, opacity: 0.8 }}
              />
            ))}
            <div
              style={{
                flex: 1,
                textAlign: "center",
                fontFamily: fonts.code,
                fontSize: 22,
                color: colors.secondary,
              }}
            >
              bash — 80×24
            </div>
          </div>

          {/* terminal content */}
          <div
            style={{
              padding: spacing.md,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            {lines.map((line, i) => {
              const cfg = STATUS_CONFIG[line.type];
              const text = getTypedText(line, i);
              const cursor = showCursor(line, i);
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: spacing.xs,
                    opacity: getLineOpacity(i),
                  }}
                >
                  {line.type === "command" && (
                    <span
                      style={{
                        fontFamily: fonts.code,
                        fontSize: 26,
                        color: "#6FCF97",
                        lineHeight: "1.7",
                        flexShrink: 0,
                      }}
                    >
                      {prompt}
                    </span>
                  )}
                  <span
                    style={{
                      fontFamily: fonts.code,
                      fontSize: 26,
                      color: cfg.color,
                      lineHeight: "1.7",
                      whiteSpace: "pre",
                    }}
                  >
                    {cfg.prefix}{text}
                    {cursor && (
                      <span
                        style={{
                          display: "inline-block",
                          width: 14,
                          height: "1em",
                          backgroundColor: "#6FCF97",
                          marginLeft: 2,
                          opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0,
                          verticalAlign: "text-bottom",
                        }}
                      />
                    )}
                  </span>
                </div>
              );
            })}

            {/* blinking prompt at end */}
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: spacing.xs,
                opacity: fadeIn(frame, termIn + lines.length * UNIT * 0.6, UNIT),
              }}
            >
              <span style={{ fontFamily: fonts.code, fontSize: 26, color: "#6FCF97", lineHeight: "1.7" }}>
                {prompt}
              </span>
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: "1em",
                  backgroundColor: "#6FCF97",
                  opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0,
                  verticalAlign: "text-bottom",
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
