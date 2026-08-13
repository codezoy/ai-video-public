"""Scene Quality Layer (S4.7) — 검사 + 자동 보정.

LLM이 생성한 scenes.json을 render 전에 순회하여
RULE-01 ~ RULE-05 를 적용, 자동 보정 후 scenes.json을 덮어쓴다.
scene_quality_report.json을 run_dir에 저장한다.

반환값: {"status": "PASS"|"WARN"|"FAIL", "corrections": int, "report": list}
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# generic title 패턴 — 이런 문자열이 hero_title.title 에 단독으로 들어오면 RULE-01 적용
_GENERIC_TITLE_PATTERNS = re.compile(
    r"^(문제\s*제기|기본\s*개념|AI의?\s*약점|서론|본론|결론|도입|마무리|"
    r"개요|정리|요약|소개|시작|끝|핵심|핵심\s*내용|학습\s*목표|학습\s*내용|"
    r"주요\s*내용|내용\s*정리|오늘의\s*주제|강의\s*목표|강의\s*내용)$",
    re.IGNORECASE,
)

_FORBIDDEN_FALLBACKS = {"N/A", "TODO", "내용 없음", "없음", "미정", "추후 추가"}


# ── 프로젝트 제목 결정 ────────────────────────────────────────────────────────

def _resolve_project_title(topic: str, input_path: "Path | None" = None) -> str:
    """사용자 친화적 프로젝트 제목을 결정한다.

    우선순위:
      A) input_path 파일의 첫 번째 H1 (# 제목)
      C) slug prettify (하이픈/언더스코어 → 공백, 단어 첫글자 대문자)
    """
    if input_path is not None:
        try:
            p = Path(input_path) if not isinstance(input_path, Path) else input_path
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped[2:].strip()
                        if title:
                            log.debug("_resolve_project_title: H1='%s' from %s", title, p.name)
                            return title
        except Exception as exc:  # noqa: BLE001
            log.warning("_resolve_project_title: H1 추출 실패 (%s) — slug fallback", exc)

    # OPTION C fallback: slug → Title Case
    slug = str(topic).replace("-", " ").replace("_", " ").strip()
    return slug.title() if slug else topic


# ── 텍스트 압축 ───────────────────────────────────────────────────────────────

def _extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """문장에서 핵심 명사/구 3~5개를 추출한다."""
    # 불용어 제거 후 공백/구두점 분리
    stopwords = {
        "및", "또는", "그리고", "하여", "이며", "으로", "에서", "하는", "있는",
        "위한", "통해", "따른", "대한", "관련", "경우", "때문에", "이후", "이전",
        "기반", "함께", "모든", "각각", "이를", "것을", "것이", "것은", "것의",
        "있다", "한다", "된다", "된다", "한다", "하다", "이다",
    }
    tokens = re.split(r"[,\s·/\(\)\[\]]+", text)
    keywords = [
        t.strip() for t in tokens
        if len(t.strip()) >= 2 and t.strip() not in stopwords
    ]
    # 중복 제거, 순서 유지
    seen: set[str] = set()
    unique: list[str] = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique[:max_keywords]


def _compress_text(text: str) -> str:
    """120자 초과 본문을 핵심 키워드 나열로 압축한다."""
    keywords = _extract_keywords(text, max_keywords=5)
    if not keywords:
        # 마지막 수단: 앞 40자
        return text[:40] + "…"
    return " · ".join(keywords)


# ── Rule 적용 ─────────────────────────────────────────────────────────────────

def _apply_rule_01(scene: dict, project_title: str, report: list) -> bool:
    """RULE-01: hero_title 영역에 generic 메인 제목 → project title로 교체."""
    if scene.get("template_type") != "hero_title":
        return False
    vd = scene.get("visual_data") or {}
    title = str(vd.get("title", "")).strip()
    if not title or not _GENERIC_TITLE_PATTERNS.match(title):
        return False

    before = title
    vd["title"] = project_title
    scene["visual_data"] = vd
    report.append({
        "scene": scene.get("id", "?"),
        "rule": "RULE-01",
        "action": "REPLACE_TITLE",
        "before": before,
        "after": project_title,
    })
    log.info("RULE-01: scene=%s title '%s' → '%s'", scene.get("id"), before, project_title)
    return True


def _apply_rule_02(scene: dict, report: list) -> bool:
    """RULE-02: 카드 본문 80자 초과 WARN, 120자 초과 AUTO_COMPRESS."""
    vd = scene.get("visual_data") or {}
    corrected = False

    # Keyword-like templates: keywords/tags/items 리스트의 각 항목
    if scene.get("template_type") in {"pill_tags", "border_cards"}:
        keywords = vd.get("keywords") or vd.get("tags") or vd.get("items") or []
        if isinstance(keywords, list):
            new_keywords = []
            for kw in keywords:
                if not isinstance(kw, str):
                    new_keywords.append(kw)
                    continue
                if len(kw) > 120:
                    compressed = _compress_text(kw)
                    report.append({
                        "scene": scene.get("id", "?"),
                        "rule": "RULE-02",
                        "action": "AUTO_COMPRESS",
                        "before_length": len(kw),
                        "after_length": len(compressed),
                    })
                    new_keywords.append(compressed)
                    corrected = True
                    log.info("RULE-02: scene=%s keyword compressed %d→%d", scene.get("id"), len(kw), len(compressed))
                elif len(kw) > 80:
                    report.append({
                        "scene": scene.get("id", "?"),
                        "rule": "RULE-02",
                        "action": "WARN",
                        "before_length": len(kw),
                    })
                    new_keywords.append(kw)
                    log.warning("RULE-02: scene=%s keyword WARN length=%d", scene.get("id"), len(kw))
                else:
                    new_keywords.append(kw)
            target_key = "tags" if scene.get("template_type") == "pill_tags" else "items"
            vd[target_key] = new_keywords

    # flow_steps / summary_card / timeline: 각 항목의 body/description
    body_fields_map = {
        "flow_steps": ("steps", "body"),
        "summary_card": ("takeaways", None),
        "timeline": ("events", "description"),
        "table_compare": ("rows", None),
    }
    ttype = scene.get("template_type", "")
    if ttype in body_fields_map:
        list_key, body_key = body_fields_map[ttype]
        items = vd.get(list_key, [])
        if isinstance(items, list):
            new_items = []
            for item in items:
                if isinstance(item, str):
                    if len(item) > 120:
                        compressed = _compress_text(item)
                        report.append({
                            "scene": scene.get("id", "?"),
                            "rule": "RULE-02",
                            "action": "AUTO_COMPRESS",
                            "before_length": len(item),
                            "after_length": len(compressed),
                        })
                        new_items.append(compressed)
                        corrected = True
                    elif len(item) > 80:
                        report.append({
                            "scene": scene.get("id", "?"),
                            "rule": "RULE-02",
                            "action": "WARN",
                            "before_length": len(item),
                        })
                        new_items.append(item)
                    else:
                        new_items.append(item)
                elif isinstance(item, dict) and body_key:
                    body = item.get(body_key, "")
                    if isinstance(body, str) and len(body) > 120:
                        compressed = _compress_text(body)
                        item = {**item, body_key: compressed}
                        report.append({
                            "scene": scene.get("id", "?"),
                            "rule": "RULE-02",
                            "action": "AUTO_COMPRESS",
                            "before_length": len(body),
                            "after_length": len(compressed),
                        })
                        corrected = True
                    elif isinstance(body, str) and len(body) > 80:
                        report.append({
                            "scene": scene.get("id", "?"),
                            "rule": "RULE-02",
                            "action": "WARN",
                            "before_length": len(body),
                        })
                    new_items.append(item)
                else:
                    new_items.append(item)
            vd[list_key] = new_items

    scene["visual_data"] = vd
    return corrected


def _apply_rule_03(scene: dict, report: list) -> bool:
    """RULE-03: 빈 카드/항목 → 의미 있는 fallback."""
    vd = scene.get("visual_data") or {}
    ttype = scene.get("template_type", "")
    corrected = False

    def _is_empty(val: Any) -> bool:
        if val is None:
            return True
        if isinstance(val, (list, dict, str)) and not val:
            return True
        return False

    def _fallback_from_narration(scene_: dict) -> str:
        narration = scene_.get("narration", "")
        kws = _extract_keywords(narration, max_keywords=3)
        return " · ".join(kws) if kws else scene_.get("title", "핵심 내용")

    list_keys = {
        "pill_tags": "tags",
        "border_cards": "items",
        "flow_steps": "steps",
        "timeline": "events",
        "summary_card": "takeaways",
        "architecture_tree": "nodes",
    }

    if ttype in list_keys:
        key = list_keys[ttype]
        val = vd.get(key)
        if _is_empty(val):
            fallback = _fallback_from_narration(scene)
            fallback_list = [fallback] if fallback else ["핵심 포인트"]
            # forbidden fallback guard
            fallback_list = [
                f if f not in _FORBIDDEN_FALLBACKS else _fallback_from_narration(scene)
                for f in fallback_list
            ]
            vd[key] = fallback_list
            scene["visual_data"] = vd
            report.append({
                "scene": scene.get("id", "?"),
                "rule": "RULE-03",
                "action": "FALLBACK_GENERATED",
                "field": key,
                "fallback": fallback_list,
            })
            corrected = True
            log.info("RULE-03: scene=%s field=%s fallback generated", scene.get("id"), key)

    # compare_two / before_after 빈 제목
    for field in ("left_title", "right_title", "before_title", "after_title"):
        if ttype in ("compare_two", "before_after") and _is_empty(vd.get(field)):
            fallback = _fallback_from_narration(scene)
            vd[field] = fallback
            scene["visual_data"] = vd
            report.append({
                "scene": scene.get("id", "?"),
                "rule": "RULE-03",
                "action": "FALLBACK_GENERATED",
                "field": field,
                "fallback": fallback,
            })
            corrected = True

    # quote_highlight 빈 quote
    if ttype == "quote_highlight" and _is_empty(vd.get("quote")):
        fallback = _fallback_from_narration(scene)
        vd["quote"] = fallback
        scene["visual_data"] = vd
        report.append({
            "scene": scene.get("id", "?"),
            "rule": "RULE-03",
            "action": "FALLBACK_GENERATED",
            "field": "quote",
            "fallback": fallback,
        })
        corrected = True

    return corrected


def _apply_rule_04(scene: dict, report: list) -> bool:
    """RULE-04: 필수 필드 누락 → render 가능한 최소 구조 생성."""
    try:
        import template_schema as _ts  # type: ignore[import]
        schema = _ts.VISUAL_DATA_SCHEMA
    except ImportError:
        log.warning("RULE-04: template_schema.py not found, skipping")
        return False

    ttype = scene.get("template_type", "")
    if ttype not in schema:
        return False

    required_fields = schema[ttype].get("required", [])
    vd = scene.get("visual_data") or {}
    corrected = False

    def _is_missing(val: Any) -> bool:
        return val is None or (isinstance(val, (list, dict, str)) and not val)

    for field in required_fields:
        if _is_missing(vd.get(field)):
            # 타입별 최소 fallback
            example = schema[ttype].get("example", {}).get(field)
            if example is not None:
                vd[field] = example
            elif field in ("keywords", "steps", "events", "takeaways", "nodes", "headers"):
                vd[field] = [_extract_keywords(scene.get("narration", "핵심 내용"), 3)[0]
                             if scene.get("narration") else "핵심 내용"]
            elif field == "rows":
                vd[field] = []
            else:
                vd[field] = scene.get("title", scene.get("narration", "내용")[:30])

            scene["visual_data"] = vd
            report.append({
                "scene": scene.get("id", "?"),
                "rule": "RULE-04",
                "action": "MISSING_FIELD_FILLED",
                "field": field,
            })
            corrected = True
            log.info("RULE-04: scene=%s field=%s filled", scene.get("id"), field)

    return corrected


def _apply_rule_05(scene: dict, report: list) -> bool:
    """RULE-05: narration 외 텍스트 밀도 과다 → 축약."""
    vd = scene.get("visual_data") or {}
    ttype = scene.get("template_type", "")
    corrected = False

    # hero_title subtitle
    subtitle = vd.get("subtitle", "")
    if isinstance(subtitle, str) and len(subtitle) > 60:
        compressed = subtitle[:57] + "…"
        vd["subtitle"] = compressed
        report.append({
            "scene": scene.get("id", "?"),
            "rule": "RULE-05",
            "action": "TRUNCATE",
            "field": "subtitle",
            "before_length": len(subtitle),
            "after_length": len(compressed),
        })
        corrected = True

    # headline
    headline = vd.get("headline", "")
    if isinstance(headline, str) and len(headline) > 80:
        compressed = _compress_text(headline)
        vd["headline"] = compressed
        report.append({
            "scene": scene.get("id", "?"),
            "rule": "RULE-05",
            "action": "COMPRESS",
            "field": "headline",
            "before_length": len(headline),
            "after_length": len(compressed),
        })
        corrected = True

    # caption
    caption = scene.get("caption", "")
    if isinstance(caption, str) and len(caption) > 100:
        compressed = caption[:97] + "…"
        scene["caption"] = compressed
        report.append({
            "scene": scene.get("id", "?"),
            "rule": "RULE-05",
            "action": "TRUNCATE",
            "field": "caption",
            "before_length": len(caption),
            "after_length": len(compressed),
        })
        corrected = True

    if corrected:
        scene["visual_data"] = vd
    return corrected


# ── 메인 진입점 ──────────────────────────────────────────────────────────────

def run(
    scenes_json: Path,
    run_dir: Path,
    topic: str,
    input_path: "Path | None" = None,
) -> dict:
    """Scene Quality Layer 실행.

    scenes_json을 읽어 RULE-01~05 적용 후 덮어씀.
    run_dir/scene_quality_report.json 저장.
    반환: {"status": str, "corrections": int, "report": list}
    """
    if not scenes_json.exists():
        log.error("scenes.json 없음: %s", scenes_json)
        raise FileNotFoundError(f"scenes.json not found: {scenes_json}")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    project_title = _resolve_project_title(topic, input_path)

    report: list[dict] = []
    total_corrections = 0
    has_fail = False

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        try:
            c1 = _apply_rule_01(scene, project_title, report)
            c2 = _apply_rule_02(scene, report)
            c3 = _apply_rule_03(scene, report)
            c4 = _apply_rule_04(scene, report)
            c5 = _apply_rule_05(scene, report)
            total_corrections += sum(1 for c in (c1, c2, c3, c4, c5) if c)
        except Exception as exc:  # noqa: BLE001
            log.error("RULE 적용 실패 scene=%s: %s", scene.get("id", "?"), exc)
            report.append({
                "scene": scene.get("id", "?"),
                "rule": "RULE-ERROR",
                "action": "ERROR",
                "error": str(exc),
            })
            has_fail = True

    # 구조 손상 체크 — scenes 배열 자체가 비면 FAIL
    if not scenes:
        log.error("scenes 배열이 비어있음 — 구조 손상 FAIL")
        has_fail = True

    data["scenes"] = scenes
    scenes_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Quality Report 저장
    quality_report_path = run_dir / "scene_quality_report.json"
    quality_report = {
        "topic": topic,
        "project_title": project_title,
        "total_scenes": len(scenes),
        "total_corrections": total_corrections,
        "status": "FAIL" if has_fail else ("WARN" if report else "PASS"),
        "corrections": report,
    }
    # WARN if any corrections were made but no failures
    if not has_fail and total_corrections > 0:
        quality_report["status"] = "WARN"

    quality_report_path.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    status = quality_report["status"]
    log.info(
        "Scene Quality Layer 완료: status=%s corrections=%d report=%s",
        status, total_corrections, quality_report_path,
    )
    print(
        f"[QUALITY] status={status} corrections={total_corrections} "
        f"report={quality_report_path}",
        flush=True,
    )
    return {"status": status, "corrections": total_corrections, "report": report}
