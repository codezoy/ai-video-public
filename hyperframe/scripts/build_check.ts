/**
 * build_check.ts — TypeScript 빌드 오류 검출 스크립트
 *
 * 사용법:
 *   npx tsx scripts/build_check.ts
 *
 * stdout: JSON 형식
 *   { "success": true, "errors": [] }
 *   { "success": false, "errors": [{ "file": "...", "line": 10, "col": 5, "message": "..." }] }
 */

import { execSync } from "child_process";
import * as path from "path";

interface BuildError {
  file: string;
  line: number;
  col: number;
  message: string;
}

interface BuildResult {
  success: boolean;
  errors: BuildError[];
}

// ── tsc 오류 파싱 ─────────────────────────────────────────────────────────────

function parseTscOutput(output: string): BuildError[] {
  const errors: BuildError[] = [];
  // tsc 오류 포맷: path/to/file.ts(line,col): error TS####: message
  const pattern = /^(.+?)\((\d+),(\d+)\):\s+error\s+TS\d+:\s+(.+)$/gm;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(output)) !== null) {
    errors.push({
      file: m[1].trim(),
      line: parseInt(m[2], 10),
      col: parseInt(m[3], 10),
      message: m[4].trim(),
    });
  }
  return errors;
}

// ── remotion bundle 문법 체크 ─────────────────────────────────────────────────

function checkRemotionBundle(): BuildError[] {
  const errors: BuildError[] = [];
  try {
    execSync("npx remotion render --help", {
      cwd: path.resolve(__dirname, ".."),
      stdio: "pipe",
      timeout: 15000,
    });
  } catch (e: unknown) {
    const err = e as { stderr?: Buffer; stdout?: Buffer };
    const output = [err.stderr?.toString() ?? "", err.stdout?.toString() ?? ""].join("\n");
    if (output.includes("SyntaxError") || output.includes("error TS")) {
      errors.push({
        file: "remotion.config.ts",
        line: 0,
        col: 0,
        message: `remotion bundle 오류: ${output.slice(0, 300)}`,
      });
    }
  }
  return errors;
}

// ── 메인 ─────────────────────────────────────────────────────────────────────

function main(): void {
  const projectDir = path.resolve(__dirname, "..");
  let tscErrors: BuildError[] = [];

  try {
    execSync("npx tsc --noEmit --pretty false", {
      cwd: projectDir,
      stdio: "pipe",
      timeout: 60000,
    });
  } catch (e: unknown) {
    const err = e as { stdout?: Buffer; stderr?: Buffer };
    const output = [err.stdout?.toString() ?? "", err.stderr?.toString() ?? ""].join("\n");
    tscErrors = parseTscOutput(output);
  }

  const remotionErrors = checkRemotionBundle();
  const allErrors = [...tscErrors, ...remotionErrors];

  const result: BuildResult = {
    success: allErrors.length === 0,
    errors: allErrors,
  };

  process.stdout.write(JSON.stringify(result, null, 2));
  process.exit(result.success ? 0 : 1);
}

main();
