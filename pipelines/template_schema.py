"""Template type constants and visual_data schema definitions.

8 supported template types for structured scene visualization.
LLM generates template_type + visual_data; renderers consume these.
"""
from __future__ import annotations

from typing import Any

TEMPLATE_TYPES: tuple[str, ...] = (
    "hero_title",
    "flow_steps",
    "timeline",
    "compare_two",
    "architecture_tree",
    "table_compare",
    "summary_card",
    "quote_highlight",
    "before_after",
    # LOW-difficulty templates (Phase 1 expansion)
    "split_title",
    "border_cards",
    "number_badge_list",
    "pill_tags",
    "fullscreen_text",
    "two_column_text",
    "callout_box",
    "bracket_emphasis",
    "slide_in_list",
    "scale_pop_cards",
    # Developer / AI Engineer compositions (Phase 2)
    "code_editor",
    "terminal",
    "chat_conversation",
    # Variant templates (Phase 3 — visual diversity)
    "timeline_zigzag",
    "timeline_cards",
    "flow_steps_circle",
    "flow_steps_stair",
    "summary_card_split",
    "compare_three",
)

_TEMPLATE_SET = frozenset(TEMPLATE_TYPES)

# Remotion composition ID map (new lowercase → PascalCase composition)
COMPOSITION_ID: dict[str, str] = {
    "hero_title":        "TitleOpen",
    "flow_steps":        "FlowSteps",
    "timeline":          "Explain",
    "compare_two":       "Explain",
    "architecture_tree": "ArchTree",
    "table_compare":     "Explain",
    "summary_card":      "OutroCta",
    # new templates — map to existing compositions
    "quote_highlight": "Quote",
    "before_after":    "CompareTwo",
    # LOW-difficulty templates (Phase 1 expansion)
    "split_title":        "SplitTitle",
    "border_cards":       "BorderCards",
    "number_badge_list":  "NumberBadgeList",
    "pill_tags":          "PillTags",
    "fullscreen_text":    "FullscreenText",
    "two_column_text":    "TwoColumnText",
    "callout_box":        "CalloutBox",
    "bracket_emphasis":   "BracketEmphasis",
    "slide_in_list":      "SlideInList",
    "scale_pop_cards":    "ScalePopCards",
    # Developer / AI Engineer compositions (Phase 2)
    "code_editor":           "CodeEditorComposition",
    "terminal":              "TerminalComposition",
    "chat_conversation":     "ChatConversationComposition",
    # Variant templates (Phase 3 — visual diversity)
    "timeline_zigzag":     "Timeline",
    "timeline_cards":      "Timeline",
    "flow_steps_circle":   "FlowSteps",
    "flow_steps_stair":    "FlowSteps",
    "summary_card_split":  "CompareTwo",
    "compare_three":       "TableCompare",
    # backward compat — old UPPER_SNAKE_CASE types
    "TITLE_OPEN":  "TitleOpen",
    "EXPLAIN":     "Explain",
    "LIST_REVEAL": "ListReveal",
    "QUOTE":       "Quote",
    "OUTRO_CTA":   "OutroCta",
}

# Required keys for each template's visual_data
VISUAL_DATA_SCHEMA: dict[str, dict[str, Any]] = {
    "hero_title": {
        "required": ["title"],
        "optional": ["subtitle", "icon"],
        "example": {
            "title": "DNS 핵심",
            "subtitle": "도메인 해석",
            "icon": "dns",
        },
    },
    "flow_steps": {
        "required": ["steps"],
        "optional": ["title"],
        "example": {
            "title": "DNS 조회 흐름",
            "steps": ["도메인 입력", "DNS 캐시 확인", "루트 서버 조회", "IP 반환", "서버 접속"],
        },
    },
    "timeline": {
        "required": ["events"],
        "optional": ["title"],
        "example": {
            "title": "DNS 변화",
            "events": ["1983 시작", "1987 표준", "2010 보안"],
        },
    },
    "compare_two": {
        "required": ["left_title", "right_title"],
        "optional": ["left_items", "right_items"],
        "example": {
            "left_title": "HTTPS",
            "right_title": "VPN",
            "left_items": ["웹 트래픽 암호화", "인증서 기반", "앱 단위 적용"],
            "right_items": ["모든 트래픽 터널링", "IP 기반", "OS 단위 적용"],
        },
    },
    "architecture_tree": {
        "required": ["nodes"],
        "optional": ["title"],
        "example": {
            "title": "DNS 계층 구조",
            "nodes": ["루트 DNS", "TLD DNS (.com)", "권한 DNS (example.com)"],
        },
    },
    "table_compare": {
        "required": ["headers", "rows"],
        "optional": ["title"],
        "example": {
            "title": "레코드 타입 비교",
            "headers": ["타입", "목적", "예시"],
            "rows": [
                ["A", "도메인 → IPv4", "93.184.216.34"],
                ["AAAA", "도메인 → IPv6", "2606:2800::1"],
                ["CNAME", "별칭", "www → example.com"],
            ],
        },
    },
    "summary_card": {
        "required": ["takeaways"],
        "optional": ["title"],
        "example": {
            "title": "핵심 정리",
            "takeaways": [
                "주소 변환",
                "계층 구조",
                "캐시 관리",
            ],
        },
    },
    "quote_highlight": {
        "required": ["quote"],
        "optional": ["source"],
        "example": {
            "quote": "짧은 핵심 문장",
            "source": "앤드류 응",
        },
    },
    "before_after": {
        "required": ["before_title", "after_title"],
        "optional": ["before_items", "after_items", "title"],
        "example": {
            "title": "AI 도입 효과",
            "before_title": "도입 전",
            "after_title": "도입 후",
            "before_items": ["수동 처리", "3시간 소요", "오류 빈번"],
            "after_items": ["자동화 처리", "5분 완료", "오류 제로"],
        },
    },
    # LOW-difficulty templates (Phase 1 expansion)
    "split_title": {
        "required": ["title"],
        "optional": ["subtitle", "detail"],
        "example": {
            "title": "AI 자동화",
            "subtitle": "핵심 개념",
            "detail": "좌우 분할 레이아웃으로 강조",
        },
    },
    "border_cards": {
        "required": ["items"],
        "optional": ["title", "labels"],
        "example": {
            "title": "보더 카드",
            "items": ["항목 1", "항목 2", "항목 3"],
            "labels": ["라벨 A", "라벨 B", "라벨 C"],
        },
    },
    "number_badge_list": {
        "required": ["items"],
        "optional": ["title"],
        "example": {
            "title": "순위 목록",
            "items": ["첫 번째 항목", "두 번째 항목", "세 번째 항목"],
        },
    },
    "pill_tags": {
        "required": ["tags"],
        "optional": ["title"],
        "example": {
            "title": "키워드 태그",
            "tags": ["AI", "자동화", "LLM", "Python"],
        },
    },
    "fullscreen_text": {
        "required": ["headline"],
        "optional": ["subtext", "label"],
        "example": {
            "headline": "핵심 메시지",
            "subtext": "부가 설명",
            "label": "INSIGHT",
        },
    },
    "two_column_text": {
        "required": ["left_body", "right_body"],
        "optional": ["left_title", "right_title"],
        "example": {
            "left_title": "왼쪽",
            "left_body": "왼쪽 내용",
            "right_title": "오른쪽",
            "right_body": "오른쪽 내용",
        },
    },
    "callout_box": {
        "required": ["message"],
        "optional": ["label", "note"],
        "example": {
            "message": "강조할 핵심 메시지",
            "label": "TIP",
            "note": "추가 참고 내용",
        },
    },
    "bracket_emphasis": {
        "required": ["keyword"],
        "optional": ["context", "detail"],
        "example": {
            "keyword": "핵심 키워드",
            "context": "문맥 설명",
            "detail": "세부 정보",
        },
    },
    "slide_in_list": {
        "required": ["items"],
        "optional": ["title"],
        "example": {
            "title": "슬라이드 인 목록",
            "items": ["항목 1", "항목 2", "항목 3"],
        },
    },
    "scale_pop_cards": {
        "required": ["items"],
        "optional": ["title", "values"],
        "example": {
            "title": "팝 카드",
            "items": ["항목 1", "항목 2", "항목 3"],
            "values": ["100%", "85%", "70%"],
        },
    },
    # Developer / AI Engineer compositions (Phase 2)
    "code_editor": {
        "required": ["code"],
        "optional": ["title", "filename", "language", "highlight_lines", "focus_line", "typing"],
        "example": {
            "title": "코드 에디터",
            "filename": "main.py",
            "language": "python",
            "code": ["def hello():", "    print('Hello, World!')", "", "hello()"],
            "highlight_lines": [1],
            "focus_line": 2,
            "typing": True,
        },
    },
    "terminal": {
        "required": ["lines"],
        "optional": ["title", "prompt", "typing"],
        "example": {
            "title": "터미널",
            "prompt": "user@host:~$",
            "lines": [
                {"text": "python run_pipeline.py --topic ai", "type": "command"},
                {"text": "Pipeline started...", "type": "output"},
                {"text": "Done!", "type": "success"},
            ],
            "typing": True,
        },
    },
    "chat_conversation": {
        "required": ["messages"],
        "optional": ["title"],
        "example": {
            "title": "대화",
            "messages": [
                {"role": "user", "text": "AI란 무엇인가요?"},
                {"role": "assistant", "text": "AI는 인공지능입니다."},
            ],
        },
    },
    # Variant templates (Phase 3 — visual diversity)
    "timeline_zigzag": {
        "required": ["events"],
        "optional": ["title"],
        "example": {
            "title": "발전 과정",
            "events": ["1단계: 시작", "2단계: 성장", "3단계: 성숙", "4단계: 혁신"],
        },
    },
    "timeline_cards": {
        "required": ["events"],
        "optional": ["title"],
        "example": {
            "title": "주요 마일스톤",
            "events": ["2020 기획", "2021 개발", "2022 출시", "2023 확장"],
        },
    },
    "flow_steps_circle": {
        "required": ["steps"],
        "optional": ["title"],
        "example": {
            "title": "순환 프로세스",
            "steps": ["계획", "실행", "검증", "개선"],
        },
    },
    "flow_steps_stair": {
        "required": ["steps"],
        "optional": ["title"],
        "example": {
            "title": "단계적 성장",
            "steps": ["기초 학습", "실습 적용", "심화 이해", "전문 활용"],
        },
    },
    "summary_card_split": {
        "required": ["left_points", "right_points"],
        "optional": ["left_title", "right_title", "title"],
        "example": {
            "title": "핵심 요약",
            "left_title": "장점",
            "right_title": "고려사항",
            "left_points": ["비용 절감", "속도 향상", "자동화"],
            "right_points": ["학습 필요", "초기 설정", "모니터링"],
        },
    },
    "compare_three": {
        "required": ["col_titles", "rows"],
        "optional": ["title"],
        "example": {
            "title": "3가지 옵션 비교",
            "col_titles": ["기준", "옵션 A", "옵션 B"],
            "rows": [
                ["비용", "저렴", "보통"],
                ["속도", "빠름", "매우 빠름"],
                ["난이도", "쉬움", "어려움"],
            ],
        },
    },
}


def is_valid_template_type(template_type: str | None) -> bool:
    """Return True if template_type is in the supported set."""
    return template_type in _TEMPLATE_SET


def get_composition_id(template_type: str) -> str:
    """Map template_type to Remotion composition ID. Falls back to 'Explain'."""
    return COMPOSITION_ID.get(template_type, COMPOSITION_ID.get(template_type.upper(), "Explain"))
