import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const SRC = path.resolve(import.meta.dirname, "../../src");

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry) ? [full] : [];
  });

describe("Mock fora do bundle de produção", () => {
  it("nenhum componente/hook importa o mock estaticamente (só `await import()` quando USE_REAL_API é falso)", () => {
    const clientCode = ["components", "hooks", "app"].flatMap((dir) => sourceFiles(path.join(SRC, dir)));
    const offenders = clientCode.filter((file) =>
      /^import[^;]*from\s+["']@\/lib\/mock-(api|data)["']/m.test(readFileSync(file, "utf8"))
    );
    expect(offenders.map((file) => path.relative(SRC, file))).toEqual([]);
  });
});
