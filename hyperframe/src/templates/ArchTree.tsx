import React from "react";
import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { bg, accent, text, font_title } from "../theme/tokens";
import { colors, radius, shadow, spacing, typography } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";
import { SAFE_AREA } from "../lib/safearea";

export interface ArchTreeNode {
  label: string;
  level?: number;
}

export interface ArchTreeProps {
  title: string;
  category?: string;
  nodes: ArchTreeNode[] | string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

function normalizeNodes(raw: ArchTreeNode[] | string[]): ArchTreeNode[] {
  if (!raw || raw.length === 0) return [];
  if (typeof raw[0] === "string") {
    return (raw as string[]).map((label, i) => ({ label, level: i === 0 ? 0 : 1 }));
  }
  return raw as ArchTreeNode[];
}

export const ArchTree: React.FC<ArchTreeProps> = ({
  title,
  category,
  nodes,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const normalized = normalizeNodes(nodes);
  const root = normalized.find((n) => (n.level ?? 0) === 0) ?? normalized[0];
  let children = normalized.filter((n, i) => (n.level ?? (i === 0 ? 0 : 1)) !== 0);
  if (children.length === 0 && normalized.length > 1) {
    children = normalized.slice(1);
  }
  const childCount = Math.max(1, children.length);
  const compact = childCount >= 6;
  const childGap = compact ? spacing.sm : spacing.lg;
  const connectorColor = `${accent}55`;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg,
        fontFamily: font_title,
        padding: `${SAFE_AREA.top}px ${SAFE_AREA.right}px ${SAFE_AREA.bottom}px ${SAFE_AREA.left}px`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "grid",
          gridTemplateRows: "auto 1fr",
          rowGap: spacing.lg,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          {category && (
            <div
              style={{
                color: accent,
                fontSize: typography.label.fontSize,
                fontWeight: 700,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                opacity: fadeIn(frame, 0, unit),
              }}
            >
              {category}
            </div>
          )}
          <h2
            style={{
              color: text,
              fontSize: typography.section.fontSize,
              fontWeight: typography.section.fontWeight,
              margin: 0,
              textAlign: "center",
              opacity: fadeIn(frame, Math.round(unit * 0.4), unit),
              transform: `translateY(${slideUp(frame, Math.round(unit * 0.4), unit)}px)`,
              wordBreak: "keep-all",
            }}
          >
            {title}
          </h2>
        </div>

        <div
          style={{
            alignSelf: "center",
            justifySelf: "center",
            width: "100%",
            maxWidth: 1540,
            display: "grid",
            gridTemplateRows: "auto 112px auto",
            justifyItems: "center",
          }}
        >
          <div
            style={{
              opacity: fadeIn(frame, unit, unit),
              transform: `translateY(${slideUp(frame, unit, unit, 24)}px)`,
              zIndex: 2,
            }}
          >
            <div
              style={{
                backgroundColor: accent,
                color: bg,
                fontSize: compact ? 34 : 42,
                fontWeight: 800,
                padding: compact ? "16px 36px" : "18px 48px",
                borderRadius: radius.xl,
                boxShadow: shadow.elevated,
                textAlign: "center",
                wordBreak: "keep-all",
                maxWidth: 760,
              }}
            >
              {root?.label ?? ""}
            </div>
          </div>

          {children.length > 0 && (
            <div
              style={{
                width: "100%",
                height: 112,
                display: "grid",
                gridTemplateColumns: `repeat(${childCount}, minmax(0, 1fr))`,
                columnGap: childGap,
                position: "relative",
                opacity: fadeIn(frame, unit, unit),
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: "50%",
                  top: 0,
                  width: 3,
                  height: 56,
                  transform: "translateX(-50%)",
                  backgroundColor: connectorColor,
                  borderRadius: 2,
                }}
              />
              {children.map((_, i) => (
                <div
                  key={i}
                  style={{
                    height: 56,
                    marginTop: 56,
                    position: "relative",
                  }}
                >
                  {childCount > 1 && (
                    <div
                      style={{
                        position: "absolute",
                        left: i === 0 ? "50%" : `calc(-${childGap}px / 2)`,
                        right: i === childCount - 1 ? "50%" : `calc(-${childGap}px / 2)`,
                        top: 0,
                        height: 3,
                        backgroundColor: connectorColor,
                        borderRadius: 2,
                      }}
                    />
                  )}
                  <div
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: 0,
                      width: 3,
                      height: 56,
                      transform: "translateX(-50%)",
                      backgroundColor: connectorColor,
                      borderRadius: 2,
                    }}
                  />
                </div>
              ))}
            </div>
          )}

          {children.length > 0 && (
            <div
              style={{
                width: "100%",
                display: "grid",
                gridTemplateColumns: `repeat(${childCount}, minmax(0, 1fr))`,
                columnGap: childGap,
              }}
            >
              {children.map((child, i) => {
                const childStart = unit + Math.round(unit * 0.4) + i * Math.round(unit * 0.35);
                return (
                  <div
                    key={i}
                    style={{
                      opacity: fadeIn(frame, childStart, unit),
                      transform: `translateY(${slideUp(frame, childStart, unit, 22)}px)`,
                      backgroundColor: colors.surface,
                      color: text,
                      fontSize: compact ? 24 : 32,
                      fontWeight: 600,
                      padding: compact ? `${spacing.sm}px ${spacing.md}px` : `${spacing.md}px ${spacing.lg}px`,
                      borderRadius: radius.lg,
                      border: `1.5px solid ${accent}28`,
                      boxShadow: shadow.card,
                      textAlign: "center",
                      lineHeight: 1.35,
                      wordBreak: "keep-all",
                      minHeight: compact ? 104 : 120,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {child.label}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
