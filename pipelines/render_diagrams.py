"""S6 시각 자산 — Mermaid 다이어그램을 PNG로 변환한다.

의존성: @mermaid-js/mermaid-cli (mmdc 명령)
설치: brew install mermaid-cli  또는  npm i -g @mermaid-js/mermaid-cli
참조: 플레이북 v2 섹션 6.2 (Mermaid 파이프라인), 부록 C (패턴 카탈로그)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][render_diagrams][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[render_diagrams] {msg}")


def _check_mmdc() -> str:
    """mmdc 명령 경로를 반환한다. 없으면 설치 안내 후 EnvironmentError."""
    path = shutil.which("mmdc")
    if path:
        return path
    raise EnvironmentError(
        "[render_diagrams] mmdc 명령을 찾을 수 없습니다.\n"
        "설치 방법:\n"
        "  brew install mermaid-cli\n"
        "또는\n"
        "  npm install -g @mermaid-js/mermaid-cli"
    )


def _run_mmdc(mmdc_bin: str, mmd_path: Path, out_path: Path, theme: str) -> tuple[bool, str]:
    """mmdc 를 실행하고 (성공여부, stderr) 를 반환한다."""
    cmd = [
        mmdc_bin,
        "-i", str(mmd_path),
        "-o", str(out_path),
        "-t", theme,
        "-b", "transparent",
        "-w", "1920",
        "-H", "1080",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    success = result.returncode == 0 and out_path.exists()
    return success, result.stderr


def mermaid_to_png(
    mermaid_code: str,
    out_path: Path,
    theme: str = "dark",
) -> Path:
    """Mermaid 코드를 mmdc CLI를 통해 PNG로 렌더링한다.

    Args:
        mermaid_code: Mermaid 다이어그램 소스 코드.
        out_path: 출력 PNG 파일 경로.
        theme: Mermaid 테마 ("dark", "default", "forest", "neutral").

    Returns:
        생성된 PNG 파일의 절대 경로.

    Raises:
        EnvironmentError: mmdc 명령이 시스템에 없을 때.
        RuntimeError: 2회 재시도 후에도 렌더링 실패 시.
    """
    mmdc_bin = _check_mmdc()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    current_code = mermaid_code

    with tempfile.TemporaryDirectory() as tmpdir:
        mmd_path = Path(tmpdir) / "diagram.mmd"

        for attempt in range(1, 4):  # 초회 + 재시도 2회
            mmd_path.write_text(current_code, encoding="utf-8")
            _log(f"mmdc 실행 시도 {attempt}/3 …")
            success, stderr = _run_mmdc(mmdc_bin, mmd_path, out_path, theme)

            if success:
                _log(f"렌더 완료: {out_path}")
                return out_path

            _log(f"mmdc 실패 (시도 {attempt}): {stderr.strip()[:200]}", "warning")

            if attempt >= 3:
                break

            # 문법 오류 시 LLM 에 stderr 피드백해 수정 재시도
            fixed = _fix_mermaid_via_llm(current_code, stderr)
            if fixed is None:
                break
            current_code = fixed

    raise RuntimeError(
        f"[render_diagrams] Mermaid 렌더링 3회 모두 실패.\n"
        f"마지막 stderr: {stderr.strip()[:500]}"
    )


def _fix_mermaid_via_llm(mermaid_code: str, error_msg: str) -> str | None:
    """mmdc 오류를 LLM 에 피드백해 수정된 코드를 반환한다. 실패 시 None."""
    try:
        import sys
        import os
        # pipelines 디렉토리가 path 에 없을 때를 대비
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        from llm_client import generate

        prompt = (
            "아래 Mermaid 코드가 mmdc 렌더링 시 오류를 발생시켰다.\n"
            "오류 메시지를 참고해 문법을 수정하고 올바른 Mermaid 코드만 출력하라.\n"
            "설명, 마크다운 펜스 없이 순수 Mermaid 코드만 출력할 것.\n\n"
            f"[오류 메시지]\n{error_msg}\n\n"
            f"[원본 코드]\n{mermaid_code}"
        )
        fixed = generate(prompt, role="light")
        # ```mermaid ... ``` 래퍼 제거
        import re
        fixed = re.sub(r"^```[a-z]*\n?", "", fixed.strip())
        fixed = re.sub(r"\n?```$", "", fixed)
        return fixed.strip()
    except Exception as exc:
        _log(f"LLM 수정 실패: {exc}", "warning")
        return None


def main() -> None:
    p = argparse.ArgumentParser(
        prog="render_diagrams.py",
        description="Mermaid 코드(.mmd 또는 --code) → PNG 렌더링.",
    )
    p.add_argument("--code", metavar="MERMAID_CODE", help="Mermaid 소스 코드 (문자열 직접 입력)")
    p.add_argument("--input", metavar="FILE", help="Mermaid 소스 파일 경로 (.mmd)")
    p.add_argument("--out", required=True, metavar="FILE", help="출력 PNG 경로")
    p.add_argument("--theme", default="dark", help="Mermaid 테마 (기본: dark)")
    args = p.parse_args()

    if not args.code and not args.input:
        print("[render_diagrams] --code 또는 --input 중 하나를 지정하세요.", file=sys.stderr)
        sys.exit(1)

    mermaid_code = Path(args.input).read_text(encoding="utf-8") if args.input else args.code
    mermaid_to_png(mermaid_code, Path(args.out), theme=args.theme)


if __name__ == "__main__":
    main()
