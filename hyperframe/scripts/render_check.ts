/**
 * render_check.ts — Remotion 단일 프레임 PNG 렌더 + 경로 반환
 *
 * 사용법:
 *   npx tsx scripts/render_check.ts --comp TitleOpen --out /path/to/output.png [--frame 0]
 *
 * stdout: JSON
 *   { "success": true,  "output": "/abs/path/to/output.png" }
 *   { "success": false, "error":  "오류 메시지" }
 */

import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

interface RenderResult {
  success: boolean;
  output?: string;
  error?: string;
}

// ── CLI 파싱 ─────────────────────────────────────────────────────────────────

function parseArgs(): { comp: string; out: string; frame: number } {
  const args = process.argv.slice(2);
  let comp = "";
  let out = "";
  let frame = 0;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--comp" && args[i + 1]) comp = args[++i];
    else if (args[i] === "--out" && args[i + 1]) out = args[++i];
    else if (args[i] === "--frame" && args[i + 1]) frame = parseInt(args[++i], 10);
  }

  if (!comp || !out) {
    process.stderr.write("Usage: render_check.ts --comp <id> --out <path> [--frame <n>]\n");
    process.exit(2);
  }

  return { comp, out, frame };
}

// ── 렌더 실행 ─────────────────────────────────────────────────────────────────

function renderFrame(comp: string, outPath: string, frame: number): RenderResult {
  const absOut = path.resolve(outPath);
  const projectDir = path.resolve(__dirname, "..");
  const entryPoint = path.join(projectDir, "src", "Root.tsx");

  const outDir = path.dirname(absOut);
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  // remotion still: 단일 프레임 PNG 렌더
  const cmd = [
    "npx remotion still",
    JSON.stringify(entryPoint),
    comp,
    JSON.stringify(absOut),
    `--frame=${frame}`,
    "--image-format=png",
    "--overwrite",
    "--log=error",
  ].join(" ");

  try {
    execSync(cmd, {
      cwd: projectDir,
      stdio: "pipe",
      timeout: 120000,
    });

    // remotion still 은 그대로 absOut 에 저장됨

    if (!fs.existsSync(absOut)) {
      return { success: false, error: `렌더 완료 후 파일 없음: ${absOut}` };
    }

    return { success: true, output: absOut };
  } catch (e: unknown) {
    const err = e as { stderr?: Buffer; stdout?: Buffer; message?: string };
    const detail = [
      err.stderr?.toString() ?? "",
      err.stdout?.toString() ?? "",
      err.message ?? "",
    ].join("\n").slice(0, 500);
    return { success: false, error: detail };
  }
}

// ── 메인 ─────────────────────────────────────────────────────────────────────

function main(): void {
  const { comp, out, frame } = parseArgs();
  const result = renderFrame(comp, out, frame);
  process.stdout.write(JSON.stringify(result, null, 2));
  process.exit(result.success ? 0 : 1);
}

main();
