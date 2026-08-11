import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, typography, spacing, radius, shadow, fonts } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { SAFE_AREA } from "../lib/safearea";
import { CaptionOverlay } from "../components/CaptionOverlay";

interface CodeEditorProps {
  title: string;
  filename: string;
  language?: string;
  code: string[];
  highlight_lines?: number[];
  focus_line?: number;
  typing?: boolean;
  captionSegments?: { text: string; start: number; end: number }[] | null;
  durationInFrames?: number;
}

const LANG_COLORS: Record<string, string> = {
  python: "#8B9DC3",
  typescript: "#C9ADA7",
  javascript: "#B5C0C8",
  bash: "#9A8C98",
  json: "#C4B5A5",
  yaml: "#A8B8C8",
};

export const CodeEditorComposition: React.FC<CodeEditorProps> = ({
  title,
  filename,
  language = "python",
  code,
  highlight_lines = [],
  focus_line,
  typing = false,
  captionSegments,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const UNIT = Math.round((fps * 300) / 1000);
  const headerIn = 0;
  const codeIn = UNIT;

  const langColor = LANG_COLORS[language] ?? colors.accent;

  const totalCodeFrames = durationInFrames ? durationInFrames - codeIn - UNIT : fps * 6;
  const charsPerLine = typing ? Math.max(...code.map((l) => l.length)) : 0;
  const totalChars = code.join("").length;

  const getLineOpacity = (lineIdx: number): number => {
    const lineStart = codeIn + (lineIdx * UNIT) / 2;
    return Math.min(1, Math.max(0, fadeIn(frame, lineStart, UNIT)));
  };

  const getTypedText = (line: string, lineIdx: number): string => {
    if (!typing) return line;
    const lineStart = codeIn + (lineIdx * UNIT) / 2;
    const elapsed = Math.max(0, frame - lineStart);
    const charsVisible = Math.floor((elapsed / (fps * 0.8)) * line.length);
    return line.slice(0, Math.min(charsVisible, line.length));
  };

  const isHighlighted = (lineIdx: number) => highlight_lines.includes(lineIdx + 1);
  const isFocused = (lineIdx: number) => focus_line === lineIdx + 1;

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      {/* radial bg */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 900px 600px at 60% 40%, ${langColor}0a 0%, transparent 70%)`,
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
            display: "flex",
            flexDirection: "column",
            gap: spacing.sm,
          }}
        >
          <div
            style={{
              fontFamily: fonts.body,
              fontSize: typography.label.fontSize,
              fontWeight: typography.label.fontWeight,
              letterSpacing: "0.12em",
              color: langColor,
              textTransform: "uppercase",
            }}
          >
            {language}
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

        {/* editor panel */}
        <div
          style={{
            flex: 1,
            backgroundColor: colors.surface,
            borderRadius: radius.lg,
            border: `1px solid ${colors.border}`,
            boxShadow: shadow.elevated,
            overflow: "hidden",
            opacity: fadeIn(frame, codeIn - UNIT / 2, UNIT),
          }}
        >
          {/* title bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: spacing.md,
              padding: `${spacing.sm}px ${spacing.md}px`,
              borderBottom: `1px solid ${colors.border}`,
              backgroundColor: `${colors.bg}88`,
            }}
          >
            {/* traffic lights */}
            {["#FF5F57", "#FEBC2E", "#28C840"].map((c, i) => (
              <div
                key={i}
                style={{ width: 14, height: 14, borderRadius: "50%", backgroundColor: c, opacity: 0.8 }}
              />
            ))}
            <div style={{ flex: 1 }} />
            <div
              style={{
                fontFamily: fonts.code,
                fontSize: 22,
                color: colors.secondary,
                letterSpacing: "0.02em",
              }}
            >
              {filename}
            </div>
            <div style={{ flex: 1 }} />
          </div>

          {/* code area */}
          <div
            style={{
              display: "flex",
              padding: `${spacing.md}px 0`,
              height: "calc(100% - 52px)",
              overflow: "hidden",
            }}
          >
            {/* line numbers */}
            <div
              style={{
                minWidth: 72,
                padding: `0 ${spacing.md}px`,
                borderRight: `1px solid ${colors.border}`,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              {code.map((_, i) => (
                <div
                  key={i}
                  style={{
                    fontFamily: fonts.code,
                    fontSize: 26,
                    lineHeight: "1.7",
                    color: isFocused(i) ? langColor : colors.secondary,
                    opacity: getLineOpacity(i),
                    textAlign: "right",
                    fontWeight: isFocused(i) ? 700 : 400,
                  }}
                >
                  {i + 1}
                </div>
              ))}
            </div>

            {/* code lines */}
            <div
              style={{
                flex: 1,
                padding: `0 ${spacing.md}px`,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              {code.map((line, i) => (
                <div
                  key={i}
                  style={{
                    position: "relative",
                    opacity: getLineOpacity(i),
                    borderRadius: radius.sm,
                    backgroundColor: isFocused(i)
                      ? `${langColor}22`
                      : isHighlighted(i)
                      ? `${langColor}12`
                      : "transparent",
                    borderLeft: isFocused(i)
                      ? `3px solid ${langColor}`
                      : isHighlighted(i)
                      ? `3px solid ${langColor}66`
                      : "3px solid transparent",
                    padding: `0 ${spacing.sm}px`,
                  }}
                >
                  <span
                    style={{
                      fontFamily: fonts.code,
                      fontSize: 26,
                      lineHeight: "1.7",
                      color: isFocused(i) ? colors.text : isHighlighted(i) ? colors.text : `${colors.text}cc`,
                      fontWeight: isFocused(i) ? 600 : 400,
                      whiteSpace: "pre",
                    }}
                  >
                    {getTypedText(line, i)}
                    {typing && getTypedText(line, i).length < line.length && (
                      <span
                        style={{
                          display: "inline-block",
                          width: 2,
                          height: "1em",
                          backgroundColor: langColor,
                          marginLeft: 2,
                          opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0,
                          verticalAlign: "text-bottom",
                        }}
                      />
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
