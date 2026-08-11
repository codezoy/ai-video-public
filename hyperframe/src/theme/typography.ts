import { typography, fonts, colors } from "./designTokens";

// Pre-built style objects for each typographic role.
// Use these in React inline styles to keep templates consistent.

export const typo = {
  hero: {
    fontFamily: fonts.title,
    fontSize: typography.hero.fontSize,
    fontWeight: typography.hero.fontWeight,
    letterSpacing: typography.hero.letterSpacing,
    lineHeight: typography.hero.lineHeight,
    color: colors.text,
  },
  section: {
    fontFamily: fonts.title,
    fontSize: typography.section.fontSize,
    fontWeight: typography.section.fontWeight,
    letterSpacing: typography.section.letterSpacing,
    lineHeight: typography.section.lineHeight,
    color: colors.accent,
  },
  card: {
    fontFamily: fonts.title,
    fontSize: typography.card.fontSize,
    fontWeight: typography.card.fontWeight,
    letterSpacing: typography.card.letterSpacing,
    lineHeight: typography.card.lineHeight,
    color: colors.text,
  },
  body: {
    fontFamily: fonts.body,
    fontSize: typography.body.fontSize,
    fontWeight: typography.body.fontWeight,
    letterSpacing: typography.body.letterSpacing,
    lineHeight: typography.body.lineHeight,
    color: colors.text,
  },
  caption: {
    fontFamily: fonts.body,
    fontSize: typography.caption.fontSize,
    fontWeight: typography.caption.fontWeight,
    letterSpacing: typography.caption.letterSpacing,
    lineHeight: typography.caption.lineHeight,
    color: colors.secondary,
  },
} as const;
