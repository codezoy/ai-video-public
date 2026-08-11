import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, typography, spacing, radius, shadow, fonts } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import { SAFE_AREA } from "../lib/safearea";
import { CaptionOverlay } from "../components/CaptionOverlay";

interface DiagramNode {
  id: string;
  label: string;
  type?: "primary" | "secondary" | "external" | "storage";
  x: number; // 0–100 percentage within safe area
  y: number; // 0–100 percentage within safe area
}

interface DiagramEdge {
  from: string;
  to: string;
  label?: string;
  animated?: boolean;
}

interface ArchitectureDiagramProps {
  title: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  captionSegments?: { text: string; start: number; end: number }[] | null;
  durationInFrames?: number;
}

const NODE_TYPE_CONFIG = {
  primary:   { bg: colors.accent,          border: colors.accent,       text: colors.bg },
  secondary: { bg: colors.surface,         border: colors.borderStrong,  text: colors.text },
  external:  { bg: "#1A1D2E",              border: "#3A3D5A",            text: colors.secondary },
  storage:   { bg: "#131620",              border: colors.accent + "66", text: colors.accent },
};

export const ArchitectureDiagramComposition: React.FC<ArchitectureDiagramProps> = ({
  title,
  nodes,
  edges,
  captionSegments,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const UNIT = Math.round((fps * 300) / 1000);
  const headerIn = 0;
  const nodesIn = UNIT;
  const edgesIn = nodesIn + UNIT;

  // Diagram canvas within safe area (below header ~180px)
  const HEADER_H = 180;
  const DIAGRAM_W = SAFE_AREA.safeWidth;
  const DIAGRAM_H = SAFE_AREA.safeHeight - HEADER_H - spacing.lg;

  const NODE_W = 200;
  const NODE_H = 80;

  const nodePositions = nodes.reduce<Record<string, { cx: number; cy: number }>>((acc, n) => {
    acc[n.id] = {
      cx: (n.x / 100) * DIAGRAM_W,
      cy: (n.y / 100) * DIAGRAM_H,
    };
    return acc;
  }, {});

  const edgeProgress = (edgeIdx: number): number => {
    const start = edgesIn + edgeIdx * UNIT * 0.5;
    return Math.min(1, Math.max(0, (frame - start) / UNIT));
  };

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 1200px 700px at 50% 55%, ${colors.surface}55 0%, transparent 70%)`,
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
            Architecture
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

        {/* diagram canvas */}
        <div style={{ flex: 1, position: "relative" }}>
          {/* SVG for edges */}
          <svg
            style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "visible" }}
            viewBox={`0 0 ${DIAGRAM_W} ${DIAGRAM_H}`}
          >
            <defs>
              <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill={colors.secondary} />
              </marker>
              <marker id="arrowhead-accent" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill={colors.accent} />
              </marker>
            </defs>

            {edges.map((edge, i) => {
              const from = nodePositions[edge.from];
              const to = nodePositions[edge.to];
              if (!from || !to) return null;

              const progress = edgeProgress(i);
              const dx = to.cx - from.cx;
              const dy = to.cy - from.cy;
              const len = Math.sqrt(dx * dx + dy * dy);
              const x2 = from.cx + dx * progress;
              const y2 = from.cy + dy * progress;

              return (
                <g key={i} opacity={Math.min(1, progress * 2)}>
                  <line
                    x1={from.cx}
                    y1={from.cy}
                    x2={x2}
                    y2={y2}
                    stroke={edge.animated ? colors.accent : colors.secondary}
                    strokeWidth={edge.animated ? 2.5 : 1.5}
                    strokeDasharray={edge.animated ? "8 4" : undefined}
                    strokeDashoffset={edge.animated ? -((frame / 2) % 12) : undefined}
                    markerEnd={progress >= 0.95 ? (edge.animated ? "url(#arrowhead-accent)" : "url(#arrowhead)") : undefined}
                    opacity={0.7}
                  />
                  {edge.label && progress >= 0.6 && (
                    <text
                      x={(from.cx + to.cx) / 2}
                      y={(from.cy + to.cy) / 2 - 10}
                      textAnchor="middle"
                      fill={colors.secondary}
                      fontSize={18}
                      fontFamily={fonts.body}
                      opacity={(progress - 0.6) / 0.4}
                    >
                      {edge.label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Nodes */}
          {nodes.map((node, i) => {
            const pos = nodePositions[node.id];
            const cfg = NODE_TYPE_CONFIG[node.type ?? "secondary"];
            const nodeStart = nodesIn + i * UNIT * 0.4;
            const op = fadeIn(frame, nodeStart, UNIT);
            const sc = scaleIn(frame, nodeStart, UNIT, 0.85);

            return (
              <div
                key={node.id}
                style={{
                  position: "absolute",
                  left: pos.cx - NODE_W / 2,
                  top: pos.cy - NODE_H / 2,
                  width: NODE_W,
                  height: NODE_H,
                  opacity: op,
                  transform: `scale(${sc})`,
                  backgroundColor: cfg.bg,
                  border: `1.5px solid ${cfg.border}`,
                  borderRadius: radius.md,
                  boxShadow: shadow.card,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: `${spacing.sm}px ${spacing.md}px`,
                }}
              >
                <div
                  style={{
                    fontFamily: fonts.body,
                    fontSize: 24,
                    fontWeight: 600,
                    color: cfg.text,
                    textAlign: "center",
                    lineHeight: 1.3,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {node.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
