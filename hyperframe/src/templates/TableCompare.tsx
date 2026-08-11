import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface TableCompareProps {
  title?: string;
  headers: string[];
  rows: string[][];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export const TableCompare: React.FC<TableCompareProps> = ({
  title,
  headers,
  rows,
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

  const colCount = headers.length;
  const firstColW = "30%";
  const otherColW = `${Math.floor(70 / (colCount - 1))}%`;

  const rowFontSize = rows.length <= 4 ? typography.body.fontSize : typography.caption.fontSize + 2;
  const headerFontSize = rows.length <= 4 ? 34 : 30;
  const rowPadding = rows.length <= 4 ? spacing.lg : spacing.md;

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
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
          }}
        >
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              margin: 0,
              textAlign: "center",
              letterSpacing: typography.section.letterSpacing,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        </div>
      )}

      {/* Table */}
      <div
        style={{
          width: "100%",
          borderRadius: radius.xl,
          overflow: "hidden",
          border: `1.5px solid ${accent}25`,
          boxShadow: shadow.elevated,
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            backgroundColor: `${accent}18`,
            borderBottom: `2px solid ${accent}40`,
            opacity: headerOpacity,
            transform: `translateY(${headerY}px)`,
          }}
        >
          {headers.map((h, i) => (
            <div
              key={i}
              style={{
                width: i === 0 ? firstColW : otherColW,
                padding: `${spacing.md}px ${spacing.lg}px`,
                color: accent,
                fontSize: headerFontSize,
                fontWeight: 700,
                textAlign: i === 0 ? "left" : "center",
                borderRight: i < headers.length - 1 ? `1px solid ${accent}20` : "none",
                letterSpacing: i === 0 ? "0" : "-0.01em",
              }}
            >
              {h}
            </div>
          ))}
        </div>

        {/* Data rows */}
        {rows.map((row, rowIdx) => {
          const rowStart = unit * 2 + rowIdx * Math.round(unit * 0.7);
          const rowOpacity = fadeIn(frame, rowStart, unit);
          const rowY = slideUp(frame, rowStart, unit, 18);
          const isEven = rowIdx % 2 === 0;

          return (
            <div
              key={rowIdx}
              style={{
                display: "flex",
                backgroundColor: isEven ? `${accent}08` : colors.surface,
                borderBottom: rowIdx < rows.length - 1 ? `1px solid ${accent}15` : "none",
                opacity: rowOpacity,
                transform: `translateY(${rowY}px)`,
              }}
            >
              {row.map((cell, colIdx) => (
                <div
                  key={colIdx}
                  style={{
                    width: colIdx === 0 ? firstColW : otherColW,
                    padding: `${rowPadding}px ${spacing.lg}px`,
                    color: colIdx === 0 ? `${text}EE` : text,
                    fontSize: rowFontSize,
                    fontWeight: colIdx === 0 ? 700 : 400,
                    textAlign: colIdx === 0 ? "left" : "center",
                    lineHeight: 1.4,
                    borderRight: colIdx < row.length - 1 ? `1px solid ${accent}12` : "none",
                    wordBreak: "keep-all",
                  }}
                >
                  {cell}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
