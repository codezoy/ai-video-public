/**
 * fontManifest.ts — Remotion용 Font Manifest (assets/font_manifest.json 미러)
 *
 * assets/font_manifest.json이 단일 소스이며, 이 파일은 그 값을 TypeScript로 반영한다.
 * 값 변경 시 font_manifest.json과 반드시 동기화할 것.
 */

export type FontRole = "title" | "section" | "card" | "body" | "caption";

export interface FontSpec {
  family: string;
  weight: number;
  /** Remotion/CSS용 파일 경로 (hyperframe/public/ 기준, staticFile() 입력값) */
  remotionFile: string;
}

export const FONT_MANIFEST: Record<FontRole, FontSpec> = {
  title: {
    family: "Paperlogy",
    weight: 800,
    remotionFile: "fonts/Paperlogy-8ExtraBold.ttf",
  },
  section: {
    family: "Paperlogy",
    weight: 700,
    remotionFile: "fonts/Paperlogy-7Bold.ttf",
  },
  card: {
    family: "Paperlogy",
    weight: 700,
    remotionFile: "fonts/Paperlogy-7Bold.ttf",
  },
  body: {
    family: "Pretendard",
    weight: 400,
    remotionFile: "fonts/PretendardVariable.ttf",
  },
  caption: {
    family: "Pretendard",
    weight: 600,
    remotionFile: "fonts/PretendardVariable.ttf",
  },
};

/** 역할별 CSS font-family + font-weight 문자열 반환 */
export function getFontStyle(role: FontRole): { fontFamily: string; fontWeight: number } {
  const spec = FONT_MANIFEST[role];
  return { fontFamily: spec.family, fontWeight: spec.weight };
}

/**
 * Language → CSS font-family stack.
 * All three fonts are bundled as project assets under hyperframe/public/fonts/.
 * zh-CN places Noto Sans SC first so Simplified Chinese glyphs never fall back to tofu.
 */
export const FONT_FAMILY_BY_LANGUAGE: Readonly<Record<string, string>> = {
  ko: "Paperlogy, Pretendard, 'Noto Sans SC', sans-serif",
  en: "Pretendard, 'Noto Sans SC', sans-serif",
  "zh-CN": "'Noto Sans SC', Pretendard, sans-serif",
};

export function getFontFamily(language?: string): string {
  return FONT_FAMILY_BY_LANGUAGE[language ?? "ko"] ?? FONT_FAMILY_BY_LANGUAGE["ko"];
}
