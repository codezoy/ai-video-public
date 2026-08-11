import React from "react";
import { colors, radius, shadow, spacing } from "../theme/designTokens";

export interface CardProps {
  children: React.ReactNode;
  color?: string;
  style?: React.CSSProperties;
  variant?: "default" | "elevated" | "ghost";
}

export const Card: React.FC<CardProps> = ({
  children,
  color = colors.accent,
  style,
  variant = "default",
}) => {
  const base: React.CSSProperties = {
    padding: `${spacing.md}px ${spacing.lg}px`,
    borderRadius: radius.md,
    backgroundColor:
      variant === "ghost"
        ? "transparent"
        : variant === "elevated"
        ? colors.surface
        : `${color}12`,
    border:
      variant === "ghost"
        ? "none"
        : `1.5px solid ${color}${variant === "elevated" ? "60" : "40"}`,
    boxShadow:
      variant === "elevated"
        ? shadow.card
        : shadow.glow(color),
  };

  return (
    <div style={{ ...base, ...style }}>
      {children}
    </div>
  );
};
