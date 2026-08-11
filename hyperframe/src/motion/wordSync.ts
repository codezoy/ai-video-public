/**
 * wordSync.ts — Remotion word-sync hook
 *
 * useWordSyncTrigger: motion_anchors 배열과 현재 프레임을 받아
 * 각 bullet 의 가시성 여부를 반환한다.
 *
 * appear_at_ms 기준으로 해당 프레임 이후부터 bullet 이 visible.
 * motion_anchors 가 없으면 stagger(기존 방식) 를 그대로 사용.
 */

import { useCurrentFrame, useVideoConfig } from "remotion";
import { MotionAnchor } from "../types/scenes";

interface WordSyncResult {
  /** bullet_idx → visible 여부 */
  isVisible: (bulletIdx: number) => boolean;
  /** bullet_idx → 현재 프레임에서의 등장 진행도 (0~1) */
  progress: (bulletIdx: number) => number;
  /** word-sync 모드 사용 중 여부 */
  isWordSync: boolean;
}

const FADE_DURATION_MS = 300; // bullet 등장 fade 애니메이션 길이

/**
 * @param motionAnchors scene.motion_anchors (없으면 undefined/null)
 * @param staggerFrames  word-sync 없을 때 기존 stagger 간격 (프레임)
 * @param totalBullets   전체 bullet 개수
 */
export function useWordSyncTrigger(
  motionAnchors: MotionAnchor[] | null | undefined,
  staggerFrames: number,
  totalBullets: number
): WordSyncResult {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const hasAnchors = motionAnchors && motionAnchors.length > 0;

  if (!hasAnchors) {
    // 기존 stagger 방식 fallback
    return {
      isVisible: (idx) => frame >= idx * staggerFrames,
      progress: (idx) => {
        const startFrame = idx * staggerFrames;
        const fadeDurationFrames = Math.ceil((FADE_DURATION_MS / 1000) * fps);
        const elapsed = frame - startFrame;
        return Math.max(0, Math.min(1, elapsed / fadeDurationFrames));
      },
      isWordSync: false,
    };
  }

  // word-sync 모드: motion_anchors 기반
  const anchorMap = new Map<number, number>();
  for (const anchor of motionAnchors) {
    anchorMap.set(anchor.bullet_idx, anchor.appear_at_ms);
  }

  // anchor 없는 bullet 은 균등 배치
  const coveredIndices = new Set(anchorMap.keys());
  for (let i = 0; i < totalBullets; i++) {
    if (!coveredIndices.has(i)) {
      // 마지막 anchor 이후 or 균등
      const lastAnchorMs = Math.max(0, ...[...anchorMap.values()]);
      const extra = (i - coveredIndices.size + 1) * 800;
      anchorMap.set(i, lastAnchorMs + extra);
    }
  }

  const msPerFrame = 1000 / fps;
  const currentMs = frame * msPerFrame;
  const fadeDurationFrames = Math.ceil((FADE_DURATION_MS / 1000) * fps);

  return {
    isVisible: (idx) => {
      const appearMs = anchorMap.get(idx) ?? 0;
      return currentMs >= appearMs;
    },
    progress: (idx) => {
      const appearMs = anchorMap.get(idx) ?? 0;
      const appearFrame = appearMs / msPerFrame;
      const elapsed = frame - appearFrame;
      return Math.max(0, Math.min(1, elapsed / fadeDurationFrames));
    },
    isWordSync: true,
  };
}
