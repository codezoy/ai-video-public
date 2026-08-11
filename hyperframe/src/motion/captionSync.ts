import { useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionSegment } from "../types/scenes";

interface CaptionSyncResult {
  currentCaption: string;
  isActive: boolean;
  progress: number;
  currentWord: string;
  currentWordIdx: number;
}

export function useCaptionSync(
  captionSegments: CaptionSegment[] | null | undefined,
  fadeMs: number = 200
): CaptionSyncResult {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!captionSegments || captionSegments.length === 0) {
    return { currentCaption: "", isActive: false, progress: 0, currentWord: "", currentWordIdx: -1 };
  }

  const msPerFrame = 1000 / fps;
  const currentMs = frame * msPerFrame;

  let active: CaptionSegment | null = null;
  for (const seg of captionSegments) {
    if (currentMs >= seg.start_ms && currentMs < seg.end_ms) {
      active = seg;
      break;
    }
  }

  if (!active) {
    return { currentCaption: "", isActive: false, progress: 0, currentWord: "", currentWordIdx: -1 };
  }

  const elapsed = currentMs - active.start_ms;
  const fadeProgress = Math.min(1, elapsed / fadeMs);

  let currentWord = "";
  let currentWordIdx = -1;

  if (active.word_timestamps && active.word_timestamps.length > 0) {
    for (let i = 0; i < active.word_timestamps.length; i++) {
      const wt = active.word_timestamps[i];
      if (currentMs >= wt.start_ms && currentMs < wt.end_ms) {
        currentWord = wt.word;
        currentWordIdx = i;
        break;
      }
    }
    if (currentWordIdx === -1 && currentMs < active.word_timestamps[0].start_ms) {
      currentWordIdx = 0;
      currentWord = active.word_timestamps[0].word;
    }
  }

  return {
    currentCaption: active.text,
    isActive: true,
    progress: fadeProgress,
    currentWord,
    currentWordIdx,
  };
}
