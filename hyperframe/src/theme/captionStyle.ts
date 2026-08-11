import { getFontStyle } from "./fontManifest";

export type CaptionPosition = "bottom" | "center" | "top";

export type CaptionStyleConfig = {
  position: CaptionPosition;
  align: "center" | "left";
  fontFamily: string;
  fontWeight: number;
  fontSize: number;
  color: string;
  highlightColor: string;
  backgroundColor: string;
  backgroundOpacity: number;
  borderRadius: number;
  paddingX: number;
  paddingY: number;
  maxWidth: number;
  maxLines: number;
  safeAreaBottom: number;
  fadeMs: number;
};

const captionFont = getFontStyle("caption");

export const DEFAULT_CAPTION_STYLE: CaptionStyleConfig = {
  position: "bottom",
  align: "center",
  fontFamily: captionFont.fontFamily,
  fontWeight: captionFont.fontWeight,
  fontSize: 30,
  color: "#FFFFFF",
  highlightColor: "#FFD966",
  backgroundColor: "#111111",
  backgroundOpacity: 0.72,
  borderRadius: 14,
  paddingX: 32,
  paddingY: 12,
  maxWidth: 1400,
  maxLines: 2,
  safeAreaBottom: 80,
  fadeMs: 200,
};
