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
  durationInFrames,
  captionSegments,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const unit = Math.round((fps * 300) / 1000);

  const categoryOpacity = fadeIn(frame, 0, unit);
  const titleOpacity = fadeIn(frame, Math.round(unit * 0.4), unit);
  const titleY = slideUp(frame, Math.round(unit * 0.4), unit);
  const rootOpacity = fadeIn(frame, unit, unit);
  const rootY = slideUp(frame, unit, unit, 24);

  const normalized = normalizeNodes(nodes);
  const root = normalized.find((n) => (n.level ?? 0) === 0) ?? normalized[0];
  const children = normalized.filter((n, i) => (n.level ?? (i === 0 ? 0 : 1)) !== 0);

  const connectorColor = `${accent}45`;

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
        gap: spacing.xxl,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {category && (
          <div
            style={{
              color: accent,
              fontSize: typography.label.fontSize,
              fontWeight: 700,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              opacity: categoryOpacity,
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
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            letterSpacing: typography.section.letterSpacing,
            wordBreak: "keep-all",
          }}
        >
          {title}
        </h2>
      </div>

      {/* Hub-and-spoke diagram */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 0,
          width: "100%",
          position: "relative",
        }}
      >
        {/* Root node */}
        <div
          style={{
            opacity: rootOpacity,
            transform: `translateY(${rootY}px)`,
            zIndex: 2,
            position: "relative",
          }}
        >
          <div
            style={{
              backgroundColor: accent,
              color: bg,
              fontSize: 42,
              fontWeight: 800,
              padding: "18px 48px",
              borderRadius: radius.xl,
              letterSpacing: "-0.02em",
              boxShadow: shadow.elevated,
              textAlign: "center",
              wordBreak: "keep-all",
            }}
          >
            {root?.label ?? ""}
          </div>
        </div>

        {/* Vertical line from root to bus */}
        {children.length > 0 && (
          <div
            style={{
              width: 3,
              height: 60,
              backgroundColor: connectorColor,
              borderRadius: 2,
              opacity: rootOpacity,
            }}
          />
        )}

        {/* Horizontal bus line */}
        {children.length > 1 && (
          <div
            style={{
              position: "absolute",
              top: "calc(50% + 28px)",
              left: "5%",
              right: "5%",
              height: 3,
              backgroundColor: connectorColor,
              opacity: rootOpacity,
              borderRadius: 2,
            }}
          />
        )}

        {/* Children row */}
        {children.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              justifyContent: "center",
              alignItems: "flex-start",
              gap: spacing.xl,
              width: "100%",
              position: "relative",
            }}
          >
            {children.map((child, i) => {
              const childStart = unit + (i + 1) * Math.round(unit * 0.7);
              const childOpacity = fadeIn(frame, childStart, unit);
              const childY = slideUp(frame, childStart, unit, 28);

              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 0,
                    opacity: childOpacity,
                    transform: `translateY(${childY}px)`,
                    flex: "1 1 0",
                    maxWidth: 380,
                  }}
                >
                  {/* Vertical connector to bus */}
                  <div
                    style={{
                      width: 3,
                      height: 40,
                      backgroundColor: connectorColor,
                      borderRadius: 2,
                    }}
                  />

                  {/* Child node card */}
                  <div
                    style={{
                      backgroundColor: colors.surface,
                      color: text,
                      fontSize: 32,
                      fontWeight: 600,
                      padding: `${spacing.md}px ${spacing.lg}px`,
                      borderRadius: radius.lg,
                      border: `1.5px solid ${accent}28`,
                      boxShadow: shadow.card,
                      textAlign: "center",
                      lineHeight: 1.35,
                      wordBreak: "keep-all",
                      width: "100%",
                    }}
                  >
                    {child.label}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
