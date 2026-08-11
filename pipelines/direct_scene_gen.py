"""FAST_PATH — Direct Scene Generation.

topic + target_duration → work/scenes.json 직접 생성.
script intermediate 없이 LLM 1회 호출로 생성 (json_repair 시 최대 2회).

Provider policy:
  CLI-only: fast_scene role (gemini_cli → codex_cli)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from cost_guard import get_policy, is_provider_allowed
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import get_policy, is_provider_allowed  # type: ignore[no-redef]

try:
    from template_schema import TEMPLATE_TYPES, VISUAL_DATA_SCHEMA  # type: ignore[import]
except ImportError:  # pragma: no cover
    from pipelines.template_schema import TEMPLATE_TYPES, VISUAL_DATA_SCHEMA  # type: ignore[no-redef]

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][direct_scene_gen][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[direct_scene_gen] {msg}")

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
OUTPUT_FILE = WORK_DIR / "scenes.json"

_LEGACY_ALIASES: frozenset[str] = frozenset({"TITLE_OPEN", "EXPLAIN", "LIST_REVEAL", "QUOTE", "OUTRO_CTA"})

_ACTIVE_TEMPLATE_TYPES: list[str] = [
    t for t in TEMPLATE_TYPES
    if t in VISUAL_DATA_SCHEMA and t not in _LEGACY_ALIASES
]


def _build_visual_data_examples() -> str:
    lines = []
    for t in _ACTIVE_TEMPLATE_TYPES:
        schema = VISUAL_DATA_SCHEMA.get(t, {})
        example = schema.get("example", {})
        compact = json.dumps(example, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"{t}: {compact}")
    return "\n".join(lines) + "\n\n"


_VISUAL_DATA_EXAMPLES_STR: str = _build_visual_data_examples()


_VISUAL_TYPE_TO_TEMPLATE_HINT: dict[str, str] = {
    "single_text": "hero_title(첫 씬) 또는 flow_steps",
    "compare_two": "compare_two",
    "bullet_list": "keyword_cards 또는 flow_steps",
    "metric_highlight": "flow_steps",
}

_MAX_LLM_CALLS: int = 2
_llm_call_count: int = 0
_scene_gen_timeout: int | None = None  # set in run() after scene_count is computed
DEFAULT_SCENE_DURATION_SEC: int = 15


def _compute_cache_key(
    topic: str,
    target_duration_sec: int,
    input_path: Path | None,
    scene_plan_path: Path,
) -> str:
    """Cache key includes topic, duration, input content, and scene_plan content."""
    parts = [topic, str(target_duration_sec)]
    if input_path and input_path.exists():
        try:
            parts.append(hashlib.sha256(input_path.read_bytes()).hexdigest()[:16])
        except Exception:
            pass
    if scene_plan_path.exists():
        try:
            parts.append(hashlib.sha256(scene_plan_path.read_bytes()).hexdigest()[:16])
        except Exception:
            pass
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _pick_role() -> str:
    return "fast_scene"


def _generate_once(prompt: str, system: str) -> str:
    global _llm_call_count
    if _llm_call_count >= _MAX_LLM_CALLS:
        raise RuntimeError(
            f"[FAST_PATH_LLM_LIMIT] max_calls={_MAX_LLM_CALLS} exceeded"
        )
    _llm_call_count += 1
    role = _pick_role()
    _log(f"[FAST_PATH] LLM call {_llm_call_count}/{_MAX_LLM_CALLS} role={role} timeout={_scene_gen_timeout}s")
    from llm_client import generate  # type: ignore[import]
    kw: dict[str, object] = {"max_tokens": 8192}
    if _scene_gen_timeout is not None:
        kw["timeout_sec"] = _scene_gen_timeout
    return generate(prompt, role=role, system=system, **kw)  # type: ignore[arg-type]


def _load_scene_plan(path: Path) -> dict | None:
    """scene_plan.json 로드. 파싱 실패 시 None 반환 (fallback)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("scenes"), list):
            _log(f"[SCENE_PLAN_CONSUMER] 유효하지 않은 scene_plan (scenes 필드 없음): {path}", "warning")
            return None
        return data
    except Exception as exc:
        _log(f"[SCENE_PLAN_CONSUMER] scene_plan.json 로드 실패: {exc}", "warning")
        return None


def _build_scene_plan_context(scene_plan: dict) -> str:
    """scene_plan dict → LLM 프롬프트용 씬별 가이드 텍스트."""
    scenes = scene_plan.get("scenes", [])
    scene_count = scene_plan.get("scene_count", len(scenes))
    lines = [
        f"[Scene Plan 가이드 — 이운규식 구조 사전 분석 결과]",
        f"총 씬 수: {scene_count}개 (정확히 {scene_count}개 씬을 생성하라)",
        "",
    ]
    for s in scenes:
        sid = s.get("scene_id", "?")
        purpose = s.get("purpose", "")
        title = s.get("title", "")
        message = s.get("message", "")
        visual_type = s.get("visual_type", "")
        narration_hint = s.get("narration_hint", "")
        template_hint = _VISUAL_TYPE_TO_TEMPLATE_HINT.get(visual_type, "flow_steps")
        lines.append(f"씬 {sid} (purpose={purpose})")
        if title:
            lines.append(f"  제목: {title}")
        if message:
            lines.append(f"  핵심 메시지: {message[:80]}")
        if visual_type:
            lines.append(f"  visual_type: {visual_type} → 추천 template_type: {template_hint}")
        if narration_hint:
            lines.append(f"  나레이션 지침: {narration_hint}")
        lines.append("")
    return "\n".join(lines)


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _extract_first_json(text: str) -> str:
    """Return the first balanced {…} block from text, discarding trailing content."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


_LANG_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "ko": {
        "expert_intro": "당신은 한국어 교육 영상의 씬 구성 전문가입니다.",
        "lang_constraint": "반드시 한국어로만 응답",
        "narration_hint": "한국어 나레이션",
    },
    "en": {
        "expert_intro": "You are an expert in English educational video scene composition.",
        "lang_constraint": "Respond in English only. ALL narration, title, bullets, and visual_data text MUST be in English",
        "narration_hint": "English narration",
    },
    "zh-CN": {
        "expert_intro": "您是中文简体教育视频场景构建专家。",
        "lang_constraint": "必须只用中文（简体）回答。所有 narration、title、bullets 和 visual_data 文本必须使用中文简体",
        "narration_hint": "中文简体旁白",
    },
}


def _build_system_prompt(
    min_scenes: int, max_scenes: int, max_scene_chars: int, max_total_chars: int,
    scene_count: int = 0,
    language: str = "ko",
    min_scene_chars: int = 70,
) -> str:
    lang = _LANG_INSTRUCTIONS.get(language, _LANG_INSTRUCTIONS["ko"])
    return (
        f"{lang['expert_intro']}\n"
        f"아래 JSON 스키마를 반드시 준수하고, JSON 외의 다른 텍스트는 출력하지 마세요.\n\n"
        f"스키마:\n"
        f'{{\n'
        f'  "project": "<topic-slug>",\n'
        f'  "voice": "nova",\n'
        f'  "scenes": [\n'
        f'    {{\n'
        f'      "id": 1,\n'
        f'      "title": "씬 제목 (20자 이내)",\n'
        f'      "narration": "{lang["narration_hint"]} ({min_scene_chars}~{max_scene_chars}자)",\n'
        f'      "bullets": [\n'
        f'        {{\n'
        f'          "text": "불릿 내용",\n'
        f'          "emphasis": ["강조 단어1"],\n'
        f'          "appear_at_ms": 0,\n'
        f'          "sentence_idx": 0\n'
        f'        }}\n'
        f'      ],\n'
        f'      "visual_type": "text",\n'
        f'      "mermaid": null,\n'
        f'      "code_block": null,\n'
        f'      "card": null,\n'
        f'      "transition_in": "fade",\n'
        f'      "transition_ms": 300,\n'
        f'      "template_type": "flow_steps",\n'
        f'      "visual_data": {{}}\n'
        f'    }}\n'
        f'  ]\n'
        f'}}\n\n'
        f"[template_type 허용 목록 — 이 {len(_ACTIVE_TEMPLATE_TYPES)}개 외에는 절대 사용 금지]\n"
        f"ALLOWED ONLY: {' | '.join(_ACTIVE_TEMPLATE_TYPES)}\n"
        f"⚠ 위 목록에 없는 template_type을 생성하면 TEMPLATE_VALIDATION_FAIL로 처리된다.\n"
        f"  새로운 template_type을 창작하지 마라.\n\n"
        f"[template_type 선택 가이드]\n"
        f"- 첫 번째 씬(index 0)만: hero_title (⚠ 중간/마지막 씬에서 사용 절대 금지)\n"
        f"- 제목 변형 씬: split_title | underline_title | side_accent_title\n"
        f"- 마지막 씬: summary_card\n"
        f"- 비교/차이 설명: compare_two | two_column_text\n"
        f"- 전후 변화/변환: before_after\n"
        f"- 순서/절차/흐름: flow_steps | number_badge_list | slide_in_list\n"
        f"- 계층 구조/트리: architecture_tree\n"
        f"- 버전/역사/타임라인: timeline\n"
        f"- 표 형태 비교: table_compare\n"
        f"- 인용/명언 강조: quote_highlight\n"
        f"- 용어/키워드 나열: keyword_cards | glass_cards | border_cards | pill_tags\n"
        f"- 단일 임팩트 메시지: fullscreen_text\n"
        f"- 강조/팁/경고 박스: callout_box | bracket_emphasis\n"
        f"- 크기 대비 카드: scale_pop_cards\n"
        f"- 코드 표시 (코드/개발 주제): code_editor | terminal\n"
        f"- 대화/채팅 형식: chat_conversation\n"
        f"- 아키텍처 다이어그램: architecture_diagram | agent_workflow\n\n"
        f"[씬 구성 다양성 규칙 — 반드시 준수]\n"
        f"- 전체 씬 중 반드시 1개는 비교형 (compare_two/before_after/two_column_text), 1개는 timeline을 사용한다\n"
        f"- keyword_cards/glass_cards/border_cards/pill_tags는 핵심어 3~5개 표시 시만 사용한다 (설명문 금지)\n"
        f"- Explain-class 템플릿(flow_steps/number_badge_list/slide_in_list)은 전체에서 최대 2개만 허용한다\n"
        f"- 씬이 {min_scenes}개 이상이면 architecture_tree, table_compare, architecture_diagram 중 1개 이상 반드시 포함한다\n"
        f"- 모든 씬은 서로 다른 template_type을 사용한다 (동일 template_type 중복 금지)\n"
        f"- visual_type은 template_type에 맞게 설정:\n"
        f"  * timeline → \"timeline\"\n"
        f"  * compare_two/before_after/two_column_text → \"compare\"\n"
        f"  * hero_title/split_title/underline_title/side_accent_title → \"hero\"\n"
        f"  * 그 외 → \"text\"\n\n"
        f"[visual_data 예시]\n"
        f"{_VISUAL_DATA_EXAMPLES_STR}"
        f"[visual_data 핵심어 규칙 — 반드시 준수]\n"
        f"- visual_data는 화면에 보이는 텍스트다. narration 전체 문장을 절대 복사하지 마라.\n"
        f"- title/subtitle/source는 20자 이내, 항목/셀/키워드는 10~20자 이내 핵심어만 사용한다.\n"
        f"- 설명문, 완전한 문장, '~합니다/~입니다/~습니다' 형태 문장 금지.\n"
        f"- 화면은 핵심어만, 설명은 narration/caption에만 둔다.\n"
        f"- BAD: ['좋은 목소리는 신뢰감과 명확성을 전달해야 합니다.']\n"
        f"- GOOD: ['신뢰감', '명확성', '낮은 피로도']\n\n"
        f"[교육 품질 규칙 — 반드시 준수]\n"
        f"Rule 1 (WHY-Hook): 첫 번째 씬 narration은 반드시 '왜 ~?' 형태의 질문으로 시작한다.\n"
        f"  금지: 'X란 무엇인가', 'X의 정의', 'X의 특징', 'X는 ~이다' 로 시작하는 narration\n"
        f"  허용 예시: '왜 구글도 실패한 제품이 있을까요?' / '왜 어떤 서비스는 성공하고 어떤 서비스는 실패할까요?'\n\n"
        f"Rule 2 (실사례): 전체 씬 중 최소 1씬에 실제 서비스·기업·사건을 구체적 이름으로 언급한다.\n"
        f"  예시 풀: Dropbox, Airbnb, 토스, 배민, Notion, Slack, Google Glass, Netflix, 카카오, 쿠팡\n\n"
        f"Rule 3 (설득형 구조): WHY(문제 제기) → 사례 → 깨달음 → 개념 순서로 전개한다.\n\n"
        f"Rule 4 (summary_card): takeaways는 반드시 3개 이상, '오늘 기억할 것' 형식, 구체적 인사이트 작성.\n"
        f"  단, 화면 takeaways는 설명문이 아니라 10~20자 핵심어만 작성한다.\n"
        f"  금지 예시: ['좋은 목소리는 신뢰감과 명확성을 전달해야 합니다']\n"
        f"  허용 예시: ['성우형 아님', '신뢰가 먼저', '피로도 낮추기']\n\n"
        f"Rule 5 (교과서 금지): narration에서 '~란 무엇인가', '~의 정의는', '~의 특징은' 으로 시작 금지.\n\n"
        f"Rule 6 (Shorts 최적화): 첫 번째 씬 narration 첫 문장에서 5초 내 호기심을 유발한다.\n\n"
        f"[핵심 제약]\n"
        f"- scene 수: {'정확히 ' + str(scene_count) + '개 (각 씬 약 12~18초 분량)' if scene_count > 0 else f'{min_scenes}~{max_scenes}개'}\n"
        f"- scene당 narration: {min_scene_chars}~{max_scene_chars}자\n"
        f"- 총 narration: {max_total_chars}자 이내\n"
        f"- emphasis: scene당 최대 5개 단어\n"
        f"- visual_summary 필드 사용 금지 (template_type + visual_data 사용)\n"
        f"- {lang['lang_constraint']}\n"
        f"- JSON만 출력 (다른 텍스트 없음)\n"
    )


_LANG_EXTRA_INSTRUCTION: dict[str, str] = {
    "ko": (
        "\n[나레이션 길이 요구사항 — 반드시 준수]\n"
        "각 씬의 narration은 반드시 95자 이상 120자 이하로 작성한다.\n"
        "95자 미만인 narration은 불합격 처리되므로 내용을 충분히 채워야 한다.\n"
        "각 씬은 약 15초 분량이므로 구체적이고 교육적인 내용으로 채워야 한다."
    ),
    "en": (
        "\n[LANGUAGE REQUIREMENT — CRITICAL]\n"
        "ALL content (narration, title, bullets, visual_data values) MUST be written in ENGLISH.\n"
        "Do NOT use Korean or any other language. Generate the scenes as if the input topic were originally in English."
    ),
    "zh-CN": (
        "\n[语言要求 — 必须遵守]\n"
        "所有内容（narration、title、bullets、visual_data 中的值）必须使用中文简体编写。\n"
        "不得使用韩语或其他语言。请将输入主题视为原本就是中文内容来生成场景。\n\n"
        "[旁白长度要求 — 严格遵守]\n"
        "每个场景的 narration 必须达到 82~95 个汉字。\n"
        "不足 82 个字符的 narration 将被视为不合格，必须补充内容直到达到最低字数要求。\n"
        "每个场景需要约 15 秒的朗读时间，请确保内容充足、具体且有教育价值。"
    ),
}

# Language-aware narration char limits per scene.
# Derived from measured TTS speaking rates × 15 s target-per-scene:
#   KO  ≈ 7.35 chars/s → min 95, max 120  (measured: 1466 chars / 199.6 s)
#   EN  ≈ 12.67 chars/s → min 150, max 200 (measured: 1450 chars / 114.4 s)
#   ZH-CN ≈ 5.19 chars/s → min 82, max 95  (measured: 219 chars / 42.5 s; need ~82 for 15 s)
_LANG_MAX_NARRATION_CHARS: dict[str, int] = {
    "ko": 120,
    "en": 200,
    "zh-CN": 95,
}
_LANG_MIN_NARRATION_CHARS: dict[str, int] = {
    "ko": 95,
    "en": 150,
    "zh-CN": 82,
}


def _build_user_prompt(
    topic: str,
    target_duration_sec: int,
    min_scenes: int,
    max_scenes: int,
    context_hint: str = "",
    scene_plan_context: str = "",
    scene_count: int = 0,
    language: str = "ko",
) -> str:
    scene_count_str = (
        f"정확히 {scene_count}개 (각 씬 약 12~18초 분량, 내부적으로 씬별 역할을 먼저 계획한 뒤 scenes JSON만 출력)"
        if scene_count > 0
        else f"{min_scenes}~{max_scenes}개"
    )
    parts = [
        f"topic: {topic}",
        f"target_duration: {target_duration_sec}초",
        f"scene 수: {scene_count_str}",
        "",
        "위 topic에 대해 핵심 개념을 압축한 교육 영상 씬 구성을 JSON으로 생성하라.",
        "이운규식 구조(WHY→사례→깨달음→개념→정리)를 압축 적용하라.",
        "",
        "[필수 요구사항]",
        "1. 첫 번째 씬: '왜 ~?' 형태의 WHY-Hook 질문으로 시작 (교과서 정의 금지)",
        "2. 중간 씬: 주제 관련 실제 서비스·기업·사건 최소 1개 구체적 언급",
        "3. 마지막 씬(summary_card): '오늘 기억할 것' takeaways 3개 이상, 구체적 인사이트",
        "4. 전체 흐름: 정의 나열이 아니라 '왜 중요한가'로 시작해 설득한다",
    ]
    extra = _LANG_EXTRA_INSTRUCTION.get(language, "")
    if extra:
        parts.append(extra)
    if scene_plan_context:
        parts.append(f"\n{scene_plan_context}")
    if context_hint:
        parts.append(f"\n[참고 맥락]\n{context_hint[:400]}")
    return "\n".join(parts)


def _validate_scenes(data: dict, profile_cfg: dict, scene_count: int = 0) -> list[str]:
    errors: list[str] = []
    scenes = data.get("scenes", [])

    min_s = profile_cfg["min_scenes"]
    max_s = profile_cfg["max_scenes"]

    if scene_count > 0 and len(scenes) != scene_count:
        errors.append(
            f"[SCENE_COUNT_MISMATCH] expected={scene_count} actual={len(scenes)}"
        )
    max_scene_chars = profile_cfg["max_scene_narration_chars"]
    max_total_chars = profile_cfg["max_total_narration_chars"]

    if scene_count == 0 and not (min_s <= len(scenes) <= max_s):
        errors.append(f"scene_count={len(scenes)} not in [{min_s}, {max_s}]")

    total_narration = 0
    for s in scenes:
        narration = s.get("narration", "")
        if not narration.strip():
            errors.append(f"scene {s.get('id')}: narration empty")
        n_len = len(narration)
        total_narration += n_len
        if n_len > max_scene_chars:
            errors.append(f"scene {s.get('id')}: narration {n_len} > {max_scene_chars}")

        emphasis_total = sum(len(b.get("emphasis", [])) for b in s.get("bullets", []))
        if emphasis_total > 5:
            errors.append(f"scene {s.get('id')}: emphasis {emphasis_total} > 5")

    if total_narration > max_total_chars:
        errors.append(f"total_narration={total_narration} > {max_total_chars}")

    # template_type + visual_data validation
    try:
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in __import__("sys").path:
            __import__("sys").path.insert(0, pipelines_dir)
        from template_validator import validate_scene  # type: ignore[import]
        for s in scenes:
            t_errors = validate_scene(s)
            errors.extend(t_errors)
    except ImportError:
        pass

    return errors


def _ensure_scene_fields(scenes: list[dict]) -> list[dict]:
    for i, scene in enumerate(scenes):
        scene.setdefault("id", i + 1)
        scene.setdefault("narration_source", None)
        scene.setdefault("audio_path", None)
        scene.setdefault("word_timestamps", None)
        scene.setdefault("motion_anchors", None)
        scene.setdefault("template_type", None)
        scene.setdefault("visual_type", "text")
        scene.setdefault("mermaid", None)
        scene.setdefault("code_block", None)
        scene.setdefault("card", None)
        scene.setdefault("transition_in", "fade")
        scene.setdefault("transition_ms", 300)
        bullets = scene.get("bullets", [])
        migrated: list[dict] = []
        for j, b in enumerate(bullets):
            if isinstance(b, str):
                migrated.append({
                    "text": b, "emphasis": [], "appear_at_ms": j * 3000, "sentence_idx": j,
                })
            else:
                migrated.append(b)
        scene["bullets"] = migrated
    return scenes


def run(
    topic: str,
    target_duration_sec: int,
    force: bool = False,
    input_path: Path | None = None,
    language: str = "ko",
) -> None:
    """FAST_PATH 직접 씬 생성."""
    global _llm_call_count, WORK_DIR, OUTPUT_FILE
    _llm_call_count = 0
    # re-evaluate at call time: run_pipeline sets os.environ["WORK_DIR"] = run_dir
    # before importing this module, so module-level OUTPUT_FILE may be stale on
    # the second+ run (Python caches modules in sys.modules after first import).
    WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
    OUTPUT_FILE = WORK_DIR / "scenes.json"

    scene_plan_path = Path(os.getenv("WORK_DIR", str(ROOT / "work"))) / "content_adapter" / "scene_plan.json"

    raw_order = ["gemini_cli", "codex_cli"]
    provider_order = ",".join(p for p in raw_order if is_provider_allowed(p))
    policy = get_policy()
    policy_summary = ",".join(
        f"{key}={str(value).lower()}" for key, value in sorted(policy.items())
    )
    print(
        f"[COST_GUARD] {policy_summary}"
        f" provider_order={provider_order}",
        flush=True,
    )

    from generation_profiles import select_profile  # type: ignore[import]
    profile_name, profile_cfg = select_profile(target_duration_sec)

    min_scenes = profile_cfg["min_scenes"]
    max_scenes = profile_cfg["max_scenes"]  # used in prompts only; clamp uses _SCENE_FIRST_MAX
    max_scene_chars = profile_cfg["max_scene_narration_chars"]
    max_total_chars = profile_cfg["max_total_narration_chars"]

    # Dynamic cap: no hard 60-scene limit for long-form videos.
    # For target ≤ 900s: cap at 60; for longer: cap = round(target / 15) so all scenes are generated.
    _SCENE_FIRST_MAX = max(60, round(target_duration_sec / DEFAULT_SCENE_DURATION_SEC))
    scene_count_raw = round(target_duration_sec / DEFAULT_SCENE_DURATION_SEC)
    scene_count = max(min_scenes, min(scene_count_raw, _SCENE_FIRST_MAX))

    # Override with language-aware narration limits so each scene stays ~15 s
    min_scene_chars: int = 70  # default (profile-agnostic fallback)
    if language in _LANG_MAX_NARRATION_CHARS:
        lang_max = _LANG_MAX_NARRATION_CHARS[language]
        lang_min = _LANG_MIN_NARRATION_CHARS.get(language, 70)
        _log(
            f"[LANG_NARRATION_LIMIT] {language}: max {max_scene_chars}→{lang_max},"
            f" min 70→{lang_min} chars/scene",
            "info",
        )
        max_scene_chars = lang_max
        min_scene_chars = lang_min
        max_total_chars = lang_max * scene_count

    global _scene_gen_timeout
    from llm_router import calc_dynamic_llm_timeout  # type: ignore[import]
    _scene_gen_timeout = calc_dynamic_llm_timeout(scene_count)

    _log(
        f"[FAST_PATH] topic={topic} target={target_duration_sec}s "
        f"profile={profile_name} min_scenes={min_scenes} "
        f"scene_count={scene_count} (raw={scene_count_raw}) timeout={_scene_gen_timeout}s"
    )
    print(
        f"[SCENE_FIRST] target_duration={target_duration_sec}s"
        f" scene_count={scene_count}"
        f" formula=round({target_duration_sec}/{DEFAULT_SCENE_DURATION_SEC})={scene_count_raw}→clamp[{min_scenes},{_SCENE_FIRST_MAX}]",
        flush=True,
    )

    hash_val = _compute_cache_key(topic, target_duration_sec, input_path, scene_plan_path)
    hash_file = OUTPUT_FILE.with_suffix(".sha")
    if OUTPUT_FILE.exists() and hash_file.exists() and not force:
        if hash_file.read_text().strip() == hash_val:
            _log(f"스킵: {OUTPUT_FILE} (해시 일치)", "warning")
            print(
                f"[FAST_PATH_LLM_LIMIT] max_calls={_MAX_LLM_CALLS}"
                " actual_calls=0 status=SKIP",
                flush=True,
            )
            return

    context_hint = ""
    if input_path and input_path.exists():
        try:
            context_hint = input_path.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass

    scene_plan_context = ""
    if scene_plan_path.exists():
        scene_plan = _load_scene_plan(scene_plan_path)
        if scene_plan is not None:
            scene_plan_context = _build_scene_plan_context(scene_plan)
            scene_count_from_plan = scene_plan.get("scene_count", len(scene_plan.get("scenes", [])))
            _log(
                f"[SCENE_PLAN_CONSUMER] source={scene_plan_path.relative_to(ROOT)}"
                f" scene_count={scene_count_from_plan}"
            )
            print(
                f"[SCENE_PLAN_CONSUMER]"
                f" source=scene_plan.json"
                f" scene_count={scene_count_from_plan}",
                flush=True,
            )
        else:
            _log("[SCENE_PLAN_CONSUMER] 로드 실패 — fallback=direct_scene_gen_default", "warning")
            print("[SCENE_PLAN_CONSUMER] fallback=direct_scene_gen_default", flush=True)
    else:
        _log("[SCENE_PLAN_CONSUMER] scene_plan.json 없음 — fallback=direct_scene_gen_default")
        print("[SCENE_PLAN_CONSUMER] fallback=direct_scene_gen_default", flush=True)

    system = _build_system_prompt(min_scenes, max_scenes, max_scene_chars, max_total_chars, scene_count, language, min_scene_chars)
    user = _build_user_prompt(
        topic, target_duration_sec, min_scenes, max_scenes, context_hint, scene_plan_context, scene_count, language
    )

    parsed: dict | None = None
    raw = _generate_once(user, system)
    try:
        parsed = json.loads(_extract_first_json(_strip_markdown_fence(raw)))
    except json.JSONDecodeError as exc:
        _log(f"JSON 파싱 실패 (attempt 1): {exc} — json_repair 시도", "warning")
        repair_prompt = f"다음 텍스트를 올바른 JSON으로 수정하라. JSON만 출력:\n\n{raw}"
        raw2 = _generate_once(repair_prompt, "JSON만 출력하라.")
        try:
            parsed = json.loads(_extract_first_json(_strip_markdown_fence(raw2)))
        except json.JSONDecodeError as exc2:
            _log(f"JSON 파싱 2회 모두 실패: {exc2}", "error")

    status = "PASS" if _llm_call_count <= _MAX_LLM_CALLS else "FAIL"
    print(
        f"[FAST_PATH_LLM_LIMIT] max_calls={_MAX_LLM_CALLS}"
        f" actual_calls={_llm_call_count} status={status}",
        flush=True,
    )

    if parsed is None:
        _log("scenes.json 생성 실패", "error")
        print(
            f"[FAST_PATH_FAIL] reason=provider_exhausted"
            f" llm_calls={_llm_call_count}"
            f" allow_claude_api={str(is_provider_allowed('claude_api')).lower()}",
            flush=True,
        )
        sys.exit(1)

    parsed["project"] = topic
    parsed.setdefault("voice", "nova")
    parsed["scenes"] = _ensure_scene_fields(parsed.get("scenes", []))

    errors = _validate_scenes(parsed, profile_cfg, scene_count)
    if errors:
        for e in errors:
            _log(f"[FAST_PATH_VALIDATION] WARN: {e}", "warning")
        print(
            f"[FAST_PATH_VALIDATION] scene_count={len(parsed['scenes'])}"
            f" errors={len(errors)} status=WARN",
            flush=True,
        )
    else:
        _log("[FAST_PATH_VALIDATION] PASS")
        print(
            f"[FAST_PATH_VALIDATION] scene_count={len(parsed['scenes'])}"
            " errors=0 status=PASS",
            flush=True,
        )

    # Enforce scene count — truncate if LLM generated more than requested
    if scene_count > 0 and len(parsed["scenes"]) > scene_count:
        _log(
            f"[SCENE_COUNT_ENFORCE] truncating {len(parsed['scenes'])} → {scene_count} scenes",
            "warning",
        )
        print(
            f"[SCENE_COUNT_ENFORCE] before={len(parsed['scenes'])} after={scene_count}",
            flush=True,
        )
        parsed["scenes"] = parsed["scenes"][:scene_count]

    # Retry once if any scene narration is below the language-specific minimum.
    # Only fires when there is remaining LLM call budget (normal path uses 1 call).
    if (
        min_scene_chars > 70
        and _llm_call_count < _MAX_LLM_CALLS
        and any(len(s.get("narration", "")) < min_scene_chars for s in parsed["scenes"])
    ):
        short = [
            (i + 1, len(s.get("narration", "")))
            for i, s in enumerate(parsed["scenes"])
            if len(s.get("narration", "")) < min_scene_chars
        ]
        _log(f"[NARRATION_MIN_RETRY] scenes below min ({min_scene_chars} chars): {short} — retrying", "warning")
        print(f"[NARRATION_MIN_RETRY] short_scenes={short} min={min_scene_chars}", flush=True)
        short_details = "; ".join(f"scene {n} ({c} chars)" for n, c in short)
        retry_user = (
            user
            + f"\n\n[CORRECTION REQUIRED]\n"
            f"Previous attempt rejected: {short_details}.\n"
            f"Minimum required is {min_scene_chars} characters per narration.\n"
            f"Regenerate ALL {scene_count} scenes. Each narration MUST have "
            f"{min_scene_chars}–{max_scene_chars} characters.\n"
            f"Output ONLY valid JSON, no explanation."
        )
        try:
            raw_r = _generate_once(retry_user, system)
            parsed_r = json.loads(_extract_first_json(_strip_markdown_fence(raw_r)))
            if parsed_r and parsed_r.get("scenes"):
                parsed_r["project"] = topic
                parsed_r.setdefault("voice", "nova")
                parsed_r["scenes"] = _ensure_scene_fields(parsed_r.get("scenes", []))
                if scene_count > 0 and len(parsed_r["scenes"]) > scene_count:
                    parsed_r["scenes"] = parsed_r["scenes"][:scene_count]
                retry_short = sum(1 for s in parsed_r["scenes"] if len(s.get("narration", "")) < min_scene_chars)
                orig_short = len(short)
                if retry_short < orig_short:
                    parsed = parsed_r
                    _log("[NARRATION_MIN_RETRY] retry accepted", "info")
                    print(f"[NARRATION_MIN_RETRY] accepted retry_short={retry_short}", flush=True)
                else:
                    _log("[NARRATION_MIN_RETRY] retry not better — keeping original", "warning")
                    print(f"[NARRATION_MIN_RETRY] kept_original retry_short={retry_short}", flush=True)
        except (RuntimeError, json.JSONDecodeError) as exc_r:
            _log(f"[NARRATION_MIN_RETRY] retry failed: {exc_r}", "warning")
            print(f"[NARRATION_MIN_RETRY] failed={exc_r}", flush=True)

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    hash_file.write_text(hash_val)
    _log(f"저장: {OUTPUT_FILE} ({len(parsed['scenes'])}개 씬)")
    print(
        f"[FAST_PATH_SCENES] scene_count={len(parsed['scenes'])}"
        f" profile={profile_name} topic={topic}",
        flush=True,
    )
