import React, { useState, useEffect } from "react";
import { Composition, registerRoot, delayRender, continueRender, cancelRender } from "remotion";
import { TitleOpen } from "./templates/TitleOpen";
import { Explain } from "./templates/Explain";
import { ListReveal } from "./templates/ListReveal";
import { Quote } from "./templates/Quote";
import { OutroCta } from "./templates/OutroCta";
import { FlowSteps } from "./templates/FlowSteps";
import { ArchTree } from "./templates/ArchTree";
import { Timeline } from "./templates/Timeline";
import { CompareTwo } from "./templates/CompareTwo";
import { TableCompare } from "./templates/TableCompare";
import { KeywordCards } from "./templates/KeywordCards";
import { SummaryCard } from "./templates/SummaryCard";
import { SplitTitle } from "./templates/SplitTitle";
import { UnderlineTitle } from "./templates/UnderlineTitle";
import { SideAccentTitle } from "./templates/SideAccentTitle";
import { GlassCards } from "./templates/GlassCards";
import { BorderCards } from "./templates/BorderCards";
import { NumberBadgeList } from "./templates/NumberBadgeList";
import { PillTags } from "./templates/PillTags";
import { FullscreenText } from "./templates/FullscreenText";
import { TwoColumnText } from "./templates/TwoColumnText";
import { CalloutBox } from "./templates/CalloutBox";
import { BracketEmphasis } from "./templates/BracketEmphasis";
import { SlideInList } from "./templates/SlideInList";
import { ScalePopCards } from "./templates/ScalePopCards";
import { CodeEditorComposition } from "./templates/CodeEditorComposition";
import { TerminalComposition } from "./templates/TerminalComposition";
import { ChatConversationComposition } from "./templates/ChatConversationComposition";
import { ArchitectureDiagramComposition } from "./templates/ArchitectureDiagramComposition";
import { AgentWorkflowComposition } from "./templates/AgentWorkflowComposition";
import { fps } from "./theme/tokens";
import { fontFaces } from "./theme/fonts";

const CANVAS_W = 1920;
const CANVAS_H = 1080;

// @font-face declarations — kept for Remotion Studio browser preview compatibility.
// Remotion renderer uses loadFonts() + delayRender pattern below for guaranteed sync.
const GlobalStyle: React.FC = () => (
  <style>{fontFaces}</style>
);

export const RemotionRoot: React.FC = () => {
  // Blocks frame capture until all project font faces (ko/en/zh-CN) are loaded.
  const [fontHandle] = useState(() => delayRender("Loading project fonts"));

  useEffect(() => {
    const requiredFonts = [
      { family: "Pretendard", weight: 400, sample: "자" },
      { family: "Pretendard", weight: 600, sample: "자" },
      { family: "Pretendard", weight: 700, sample: "자" },
      { family: "Paperlogy", weight: 800, sample: "자" },
      { family: "Noto Sans SC", weight: 400, sample: "供" },
      { family: "Noto Sans SC", weight: 700, sample: "供" },
    ];

    Promise.all(
      requiredFonts.map(({ family, weight, sample }) =>
        document.fonts.load(`${weight} 1px "${family}"`, sample)
      )
    ).then(async () => {
      await document.fonts.ready;
      const failed = requiredFonts.filter(
        ({ family, weight, sample }) =>
          !document.fonts.check(`${weight} 16px "${family}"`, sample)
      );
      if (failed.length > 0) {
        const message = failed
          .map(({ family, weight }) => `${family}:${weight}`)
          .join(", ");
        cancelRender(new Error(`[REMOTION_FONT_LOAD] failed=${message}`));
        return;
      }
      requiredFonts.forEach(({ family, weight }) => {
        console.log(`[REMOTION_FONT_LOAD] family=${family} weight=${weight} status=loaded`);
      });
      continueRender(fontHandle);
    }).catch(() => {
      cancelRender(new Error("[REMOTION_FONT_LOAD] font loading rejected"));
    });
  }, [fontHandle]);

  return (
    <>
      <GlobalStyle />
      {/* Font preload — forces Korean glyph requests before any frame is captured. */}
      <div style={{ fontFamily: "Pretendard", fontWeight: 400, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>자</div>
      <div style={{ fontFamily: "Pretendard", fontWeight: 600, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>·</div>
      <div style={{ fontFamily: "Pretendard", fontWeight: 700, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>자</div>
      <div style={{ fontFamily: "Paperlogy", fontWeight: 800, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>자</div>
      <div style={{ fontFamily: "'Noto Sans SC'", fontWeight: 400, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>供</div>
      <div style={{ fontFamily: "'Noto Sans SC'", fontWeight: 700, position: "absolute", opacity: 0, fontSize: 1, pointerEvents: "none" }}>供</div>

      <Composition
        id="TitleOpen"
        component={TitleOpen as React.ComponentType<any>}
        durationInFrames={fps * 5}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "AI 자동화 비즈니스",
          subtitle: "바이브코딩 × 오픈소스로 수익화하기",
          category: "LECTURE 01",
          durationInFrames: fps * 5,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 5 })}
      />

      <Composition
        id="Explain"
        component={Explain as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "개념 설명",
          bullets: ["첫 번째 핵심 포인트", "두 번째 핵심 포인트", "세 번째 핵심 포인트"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="ListReveal"
        component={ListReveal as React.ComponentType<any>}
        durationInFrames={fps * 10}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "핵심 목록",
          items: ["항목 1", "항목 2", "항목 3", "항목 4"],
          durationInFrames: fps * 10,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 10 })}
      />

      <Composition
        id="Quote"
        component={Quote as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          quote: "여기에 핵심 인용구나 중요한 개념을 입력합니다.",
          source: "출처 또는 저자",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="OutroCta"
        component={OutroCta as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          nextVideos: ["다음 추천 영상 제목 1", "다음 추천 영상 제목 2"],
          channelName: "채널명",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="FlowSteps"
        component={FlowSteps as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "마케팅 자동화 워크플로우",
          category: "WORKFLOW",
          steps: ["SNS 콘텐츠 기획\nAI 생성", "SNS 자동화\n오픈클로 배포", "콘텐츠 예약\n매일 발행"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="ArchTree"
        component={ArchTree as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "AI 파이프라인 구조",
          category: "ARCHITECTURE",
          nodes: [
            { label: "AI 오케스트레이터", level: 0 },
            { label: "콘텐츠 생성 에이전트", level: 1 },
            { label: "SNS 발행 에이전트", level: 1 },
            { label: "모니터링 에이전트", level: 1 },
          ],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="Timeline"
        component={Timeline as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "수익화 성장 과정",
          category: "TIMELINE",
          events: ["1주차\n아이디어 검증", "3주차\n첫 수익 발생", "8주차\n월 1,000만 원"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="CompareTwo"
        component={CompareTwo as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "A vs B 비교",
          left_title: "A 방식",
          right_title: "B 방식",
          left_items: ["장점 1: 빠른 처리 속도", "장점 2: 낮은 복잡도", "장점 3: 쉬운 유지보수"],
          right_items: ["특징 1: 높은 유연성", "특징 2: 확장 가능한 구조", "특징 3: 풍부한 기능"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="TableCompare"
        component={TableCompare as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "비교 분석",
          headers: ["구분", "A 방식", "B 방식"],
          rows: [
            ["처리 속도", "빠름 (O(1))", "보통 (O(n))"],
            ["메모리 사용", "낮음", "높음"],
            ["유연성", "제한적", "높음"],
            ["구현 복잡도", "단순", "복잡"],
          ],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="KeywordCards"
        component={KeywordCards as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "수익화까지 가기 위한 이해 필요",
          keywords: ["바이브 코딩", "비즈니스 실현", "자동화 사업"],
          icons: ["💻", "🧠", "🚀"],
          descriptions: ["도구의 활용", "BM 기획과 적용", "무한 창업 모드"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="SummaryCard"
        component={SummaryCard as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          takeaways: [
            "AI 도구 하나면 기획·제작·발행까지 혼자 가능하다",
            "바이브코딩은 아이디어를 즉시 제품으로 만드는 능력이다",
            "자동화는 시간을 팔지 않고 수익을 만드는 구조다",
          ],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="SplitTitle"
        component={SplitTitle as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "좌우 분할 레이아웃",
          subtitle: "핵심 개념 강조",
          detail: "오른쪽 패널에 상세 내용이 표시됩니다",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="UnderlineTitle"
        component={UnderlineTitle as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "밑줄 강조 제목",
          subtitle: "애니메이션 언더라인",
          label: "POINT",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="SideAccentTitle"
        component={SideAccentTitle as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "사이드 액센트 제목",
          subtitle: "왼쪽 수직 바 강조",
          tag: "KEY",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="GlassCards"
        component={GlassCards as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "글라스모피즘 카드",
          items: ["첫 번째 항목", "두 번째 항목", "세 번째 항목"],
          icons: ["💡", "🚀", "🎯"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="BorderCards"
        component={BorderCards as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "보더 카드",
          items: ["첫 번째 항목", "두 번째 항목", "세 번째 항목"],
          labels: ["라벨 A", "라벨 B", "라벨 C"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="NumberBadgeList"
        component={NumberBadgeList as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "숫자 배지 목록",
          items: ["첫 번째 핵심 포인트", "두 번째 핵심 포인트", "세 번째 핵심 포인트"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="PillTags"
        component={PillTags as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "키워드 태그 클라우드",
          tags: ["AI", "자동화", "LLM", "Python", "영상"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="FullscreenText"
        component={FullscreenText as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          headline: "핵심 메시지",
          subtext: "대형 타이포그래피로 임팩트를 전달합니다",
          label: "INSIGHT",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="TwoColumnText"
        component={TwoColumnText as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          leftTitle: "왼쪽",
          leftBody: "왼쪽 패널의 내용이 여기에 표시됩니다",
          rightTitle: "오른쪽",
          rightBody: "오른쪽 패널의 내용이 여기에 표시됩니다",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="CalloutBox"
        component={CalloutBox as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          message: "강조할 핵심 메시지를 여기에 입력합니다",
          label: "TIP",
          note: "추가 참고 내용",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="BracketEmphasis"
        component={BracketEmphasis as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          keyword: "핵심어",
          context: "키워드 문맥 설명",
          detail: "세부 정보",
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="SlideInList"
        component={SlideInList as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "슬라이드 인 목록",
          items: ["첫 번째 항목", "두 번째 항목", "세 번째 항목"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="ScalePopCards"
        component={ScalePopCards as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "스케일 팝 카드",
          items: ["항목 1", "항목 2", "항목 3"],
          values: ["100%", "85%", "70%"],
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="CodeEditorComposition"
        component={CodeEditorComposition as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "run_pipeline 분석",
          filename: "run_pipeline.py",
          language: "python",
          code: ["def run():", "    planner()", "    executor()", "    reviewer()", "    validator()"],
          highlight_lines: [2, 3],
          focus_line: 3,
          typing: true,
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="TerminalComposition"
        component={TerminalComposition as React.ComponentType<any>}
        durationInFrames={fps * 8}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "파이프라인 실행",
          prompt: "$",
          lines: [
            { text: "python pipelines/run_pipeline.py --topic ai-agent", type: "command" },
            { text: "[INFO] Loading scenes...", type: "output" },
            { text: "TTS 생성 완료 (5개 씬)", type: "success" },
            { text: "렌더링 중 메모리 부족 경고", type: "warning" },
            { text: "video.mp4 저장 완료", type: "success" },
          ],
          typing: true,
          durationInFrames: fps * 8,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 8 })}
      />

      <Composition
        id="ChatConversationComposition"
        component={ChatConversationComposition as React.ComponentType<any>}
        durationInFrames={fps * 10}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "AI 에이전트 대화",
          messages: [
            { role: "user", text: "파이프라인을 자동화해줘" },
            { role: "assistant", name: "Planner", text: "네, PLAN → ACTION → VALIDATE 3단계로 분리하겠습니다." },
            { role: "user", text: "실행 중 오류가 나면?" },
            { role: "assistant", name: "Reviewer", text: "Fail Loud 원칙에 따라 즉시 에러를 노출하고 종료합니다." },
          ],
          durationInFrames: fps * 10,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 10 })}
      />

      <Composition
        id="ArchitectureDiagramComposition"
        component={ArchitectureDiagramComposition as React.ComponentType<any>}
        durationInFrames={fps * 10}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "멀티 에이전트 아키텍처",
          nodes: [
            { id: "orchestrator", label: "Orchestrator", type: "primary", x: 50, y: 20 },
            { id: "planner",      label: "Planner",      type: "secondary", x: 20, y: 60 },
            { id: "executor",     label: "Executor",     type: "secondary", x: 50, y: 60 },
            { id: "reviewer",     label: "Reviewer",     type: "secondary", x: 80, y: 60 },
            { id: "storage",      label: "Vector DB",    type: "storage",   x: 50, y: 90 },
          ],
          edges: [
            { from: "orchestrator", to: "planner",  animated: false },
            { from: "orchestrator", to: "executor", animated: true },
            { from: "orchestrator", to: "reviewer", animated: false },
            { from: "executor",     to: "storage",  label: "embed", animated: true },
          ],
          durationInFrames: fps * 10,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 10 })}
      />

      <Composition
        id="AgentWorkflowComposition"
        component={AgentWorkflowComposition as React.ComponentType<any>}
        durationInFrames={fps * 10}
        fps={fps}
        width={CANVAS_W}
        height={CANVAS_H}
        defaultProps={{
          title: "HCHAIN 실행 흐름",
          agent_name: "HCHAIN Runtime",
          steps: [
            { label: "PLAN",     description: "미션 분해" },
            { label: "RESEARCH", description: "컨텍스트 수집" },
            { label: "ACTION",   description: "코드 실행" },
            { label: "REVIEW",   description: "결과 검토" },
            { label: "VALIDATE", description: "DoD 체크" },
            { label: "DONE",     description: "완료 보고" },
          ],
          current_step: 3,
          layout: "horizontal",
          durationInFrames: fps * 10,
        }}
        calculateMetadata={({ props }) => ({ durationInFrames: (props as any).durationInFrames ?? fps * 10 })}
      />
    </>
  );
};

registerRoot(RemotionRoot);
