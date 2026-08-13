import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, typography, spacing, radius, shadow, fonts } from "../theme/designTokens";
import { fadeIn, slideUp } from "../motion/primitives";
import { SAFE_AREA } from "../lib/safearea";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CaptionSegment } from "../types/scenes";

type Role = "user" | "assistant" | "system";

interface ChatMessage {
  role: Role;
  name?: string;
  text: string;
}

interface ChatConversationProps {
  title: string;
  messages: ChatMessage[];
  captionSegments?: CaptionSegment[] | null;
  durationInFrames?: number;
}

const ROLE_CONFIG: Record<Role, { color: string; align: "left" | "right"; label: string }> = {
  user:      { color: "#8B9DC3", align: "right",  label: "User" },
  assistant: { color: "#C9ADA7", align: "left",   label: "AI" },
  system:    { color: "#9A8C98", align: "left",   label: "System" },
};

export const ChatConversationComposition: React.FC<ChatConversationProps> = ({
  title,
  messages,
  captionSegments,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const UNIT = Math.round((fps * 300) / 1000);
  const headerIn = 0;
  const chatIn = UNIT;

  const getMsgOpacity = (idx: number) => fadeIn(frame, chatIn + idx * UNIT * 0.8, UNIT);
  const getMsgSlide = (idx: number, role: Role) => {
    const offset = slideUp(frame, chatIn + idx * UNIT * 0.8, UNIT);
    return `translateY(${offset}px)`;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 1000px 600px at 50% 50%, ${colors.surface}44 0%, transparent 70%)`,
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
            Conversation
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

        {/* chat area */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: spacing.md,
            overflowY: "hidden",
          }}
        >
          {messages.map((msg, i) => {
            const cfg = ROLE_CONFIG[msg.role];
            const isRight = cfg.align === "right";

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: isRight ? "flex-end" : "flex-start",
                  gap: spacing.xs,
                  opacity: getMsgOpacity(i),
                  transform: getMsgSlide(i, msg.role),
                }}
              >
                {/* role label */}
                <div
                  style={{
                    fontFamily: fonts.body,
                    fontSize: typography.label.fontSize,
                    fontWeight: 600,
                    letterSpacing: "0.08em",
                    color: cfg.color,
                    textTransform: "uppercase",
                    paddingLeft: isRight ? 0 : spacing.sm,
                    paddingRight: isRight ? spacing.sm : 0,
                  }}
                >
                  {msg.name ?? cfg.label}
                </div>

                {/* bubble */}
                <div
                  style={{
                    maxWidth: "72%",
                    backgroundColor: isRight ? `${cfg.color}22` : colors.surface,
                    border: `1px solid ${isRight ? `${cfg.color}44` : colors.border}`,
                    borderRadius: isRight
                      ? `${radius.lg}px ${radius.sm}px ${radius.lg}px ${radius.lg}px`
                      : `${radius.sm}px ${radius.lg}px ${radius.lg}px ${radius.lg}px`,
                    padding: `${spacing.md}px ${spacing.lg}px`,
                    boxShadow: shadow.card,
                  }}
                >
                  <div
                    style={{
                      fontFamily: fonts.body,
                      fontSize: typography.body.fontSize,
                      fontWeight: typography.body.fontWeight,
                      lineHeight: 1.55,
                      color: colors.text,
                      letterSpacing: "0em",
                    }}
                  >
                    {msg.text}
                  </div>
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
