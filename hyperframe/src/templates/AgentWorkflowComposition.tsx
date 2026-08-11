import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, typography, spacing, radius, shadow, fonts } from "../theme/designTokens";
import { fadeIn, slideUp, scaleIn } from "../motion/primitives";
import { SAFE_AREA } from "../lib/safearea";
import { CaptionOverlay } from "../components/CaptionOverlay";

interface WorkflowStep {
  label: string;
  description?: string;
  status?: "pending" | "active" | "done";
  icon?: string;
}

interface AgentWorkflowProps {
  title: string;
  agent_name?: string;
  steps: WorkflowStep[];
  current_step?: number; // 1-indexed
  layout?: "horizontal" | "vertical";
  captionSegments?: { text: string; start: number; end: number }[] | null;
  durationInFrames?: number;
}

const STATUS_CONFIG = {
  pending: { bg: colors.surface,   border: colors.border,       text: colors.secondary, badgeBg: colors.bg },
  active:  { bg: `${colors.accent}18`, border: colors.accent,   text: colors.text,      badgeBg: colors.accent },
  done:    { bg: `${colors.panelRight}18`, border: colors.panelRight, text: colors.text, badgeBg: colors.panelRight },
};

export const AgentWorkflowComposition: React.FC<AgentWorkflowProps> = ({
  title,
  agent_name,
  steps,
  current_step,
  layout = "horizontal",
  captionSegments,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const UNIT = Math.round((fps * 300) / 1000);
  const headerIn = 0;
  const stepsIn = UNIT;

  // Resolve statuses
  const resolvedSteps: (WorkflowStep & { resolvedStatus: "pending" | "active" | "done" })[] = steps.map((s, i) => {
    const stepNum = i + 1;
    let resolvedStatus: "pending" | "active" | "done" = s.status ?? "pending";
    if (current_step !== undefined) {
      if (stepNum < current_step) resolvedStatus = "done";
      else if (stepNum === current_step) resolvedStatus = "active";
      else resolvedStatus = "pending";
    }
    return { ...s, resolvedStatus };
  });

  const isHorizontal = layout === "horizontal";
  const STEP_W = isHorizontal ? Math.min(280, (SAFE_AREA.safeWidth - spacing.xl) / steps.length - spacing.md) : SAFE_AREA.safeWidth;
  const STEP_H = isHorizontal ? 240 : 100;

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 1000px 600px at 50% 50%, ${colors.accent}08 0%, transparent 70%)`,
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
          {agent_name && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: spacing.sm,
                backgroundColor: `${colors.accent}18`,
                border: `1px solid ${colors.accent}44`,
                borderRadius: radius.full,
                padding: `${spacing.xs}px ${spacing.md}px`,
                marginBottom: spacing.sm,
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: colors.accent,
                  boxShadow: `0 0 8px ${colors.accent}`,
                  animation: "pulse 1.5s ease-in-out infinite",
                }}
              />
              <span
                style={{
                  fontFamily: fonts.code,
                  fontSize: typography.label.fontSize,
                  fontWeight: 600,
                  color: colors.accent,
                  letterSpacing: "0.05em",
                }}
              >
                {agent_name}
              </span>
            </div>
          )}
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

        {/* steps */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: isHorizontal ? "row" : "column",
            alignItems: isHorizontal ? "flex-start" : "stretch",
            gap: isHorizontal ? spacing.md : spacing.sm,
          }}
        >
          {resolvedSteps.map((step, i) => {
            const stepStart = stepsIn + i * UNIT * 0.5;
            const cfg = STATUS_CONFIG[step.resolvedStatus];
            const isActive = step.resolvedStatus === "active";

            return (
              <React.Fragment key={i}>
                {/* step card */}
                <div
                  style={{
                    opacity: fadeIn(frame, stepStart, UNIT),
                    transform: `scale(${scaleIn(frame, stepStart, UNIT, 0.9)})`,
                    width: isHorizontal ? STEP_W : "100%",
                    minHeight: STEP_H,
                    backgroundColor: cfg.bg,
                    border: `1.5px solid ${cfg.border}`,
                    borderRadius: radius.lg,
                    boxShadow: isActive ? `${shadow.card}, 0 0 32px ${colors.accent}22` : shadow.card,
                    padding: `${spacing.md}px ${spacing.lg}px`,
                    display: "flex",
                    flexDirection: isHorizontal ? "column" : "row",
                    alignItems: isHorizontal ? "flex-start" : "center",
                    gap: spacing.md,
                    position: "relative",
                    overflow: "hidden",
                  }}
                >
                  {/* active pulse ring */}
                  {isActive && (
                    <div
                      style={{
                        position: "absolute",
                        inset: -2,
                        borderRadius: radius.lg + 2,
                        border: `2px solid ${colors.accent}`,
                        opacity: 0.4 + 0.3 * Math.sin((frame / fps) * Math.PI * 2),
                        pointerEvents: "none",
                      }}
                    />
                  )}

                  {/* badge */}
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: radius.md,
                      backgroundColor: cfg.badgeBg,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    {step.resolvedStatus === "done" ? (
                      <span
                        style={{
                          fontFamily: fonts.body,
                          fontSize: 22,
                          color: colors.bg,
                          fontWeight: 700,
                        }}
                      >
                        ✓
                      </span>
                    ) : (
                      <span
                        style={{
                          fontFamily: fonts.code,
                          fontSize: 20,
                          color: step.resolvedStatus === "active" ? colors.bg : colors.text,
                          fontWeight: 700,
                        }}
                      >
                        {step.icon ?? String(i + 1).padStart(2, "0")}
                      </span>
                    )}
                  </div>

                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontFamily: fonts.body,
                        fontSize: typography.caption.fontSize,
                        fontWeight: 700,
                        color: cfg.text,
                        lineHeight: 1.3,
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {step.label}
                    </div>
                    {step.description && (
                      <div
                        style={{
                          fontFamily: fonts.body,
                          fontSize: typography.label.fontSize,
                          fontWeight: 400,
                          color: colors.secondary,
                          lineHeight: 1.5,
                          marginTop: spacing.xs,
                          letterSpacing: "0em",
                        }}
                      >
                        {step.description}
                      </div>
                    )}
                  </div>
                </div>

                {/* connector arrow (between steps, not after last) */}
                {i < resolvedSteps.length - 1 && (
                  <div
                    style={{
                      opacity: fadeIn(frame, stepStart + UNIT, UNIT * 0.5),
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                      ...(isHorizontal
                        ? { width: 32, alignSelf: "center" }
                        : { height: 24, flexDirection: "column" }),
                    }}
                  >
                    <div
                      style={{
                        fontFamily: fonts.body,
                        fontSize: 28,
                        color: colors.secondary,
                        lineHeight: 1,
                        transform: isHorizontal ? "none" : "rotate(90deg)",
                      }}
                    >
                      →
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <CaptionOverlay captionSegments={captionSegments} />
    </AbsoluteFill>
  );
};
