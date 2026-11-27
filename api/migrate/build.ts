// `pnpm run build` (Workers Builds runs it first): write the generated registry and migrations,
// then build the web. A branch that is neither `production` nor `preview/*` builds nothing, so a
// `lane/*` push costs a no-op (story 137).
import { execFileSync } from "node:child_process";
import { repoRoot, writeGenerated } from "./discover";

export function shouldBuild(branch: string | undefined): boolean {
  return (
    branch === undefined ||
    branch === "" ||
    branch === "production" ||
    branch.startsWith("preview/")
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const branch = process.env.WORKERS_CI_BRANCH;
  if (!shouldBuild(branch)) {
    console.log(`build: branch ${branch} builds nothing`);
    process.exit(0);
  }
  const sha =
    process.env.WORKERS_CI_COMMIT_SHA ??
    execFileSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot }).toString().trim();
  writeGenerated(repoRoot, sha);
  execFileSync("pnpm", ["gen"], { cwd: repoRoot, stdio: "inherit" });
  execFileSync("pnpm", ["--filter", "@stockpilot/web", "build"], {
    cwd: repoRoot,
    stdio: "inherit",
  });
}
