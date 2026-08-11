export type TemplateType =
  | "TITLE_OPEN"
  | "EXPLAIN"
  | "LIST_REVEAL"
  | "QUOTE"
  | "OUTRO_CTA"
  | "FlowSteps"
  | "ArchTree"
  | null;

export type NarrationSource = "azure" | "openai" | "say" | "recorded" | null;

export interface WordTimestamp {
  word: string;
  start_ms: number;
  end_ms: number;
}

export interface MotionAnchor {
  trigger_word: string;
  appear_at_ms: number;
  bullet_idx: number;
}

export interface CaptionSegment {
  text: string;
  start_ms: number;
  end_ms: number;
  word_timestamps?: WordTimestamp[];
}

export interface SceneData {
  id: number;
  title: string;
  narration: string;
  bullets?: string[];
  visual_type?: string;
  mermaid?: string | null;
  code_block?: string | null;
  card?: Record<string, string> | null;
  transition_in?: string;
  transition_ms?: number;
  template_type?: TemplateType;
  narration_source?: NarrationSource;
  audio_path?: string | null;
  word_timestamps?: WordTimestamp[] | null;
  motion_anchors?: MotionAnchor[] | null;
  caption_segments?: CaptionSegment[] | null;
  language?: string;
}

export interface TitleOpenProps {
  title: string;
  subtitle?: string;
  category?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export interface ExplainProps {
  title: string;
  bullets: string[];
  durationInFrames: number;
  motionAnchors?: MotionAnchor[] | null;
  captionSegments?: CaptionSegment[] | null;
}

export interface ListRevealProps {
  title: string;
  items: string[];
  durationInFrames: number;
  motionAnchors?: MotionAnchor[] | null;
  captionSegments?: CaptionSegment[] | null;
}

export interface QuoteProps {
  quote: string;
  source?: string;
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

export interface OutroCtaProps {
  nextVideos?: string[];
  channelName?: string;
  durationInFrames: number;
}

export interface FlowStepsProps {
  title: string;
  category?: string;
  steps: string[];
  durationInFrames: number;
  captionSegments?: CaptionSegment[] | null;
}

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
