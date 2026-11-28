// LO279: Admin's Needs you lists issues labelled prototype-waiting, with links.
import { Hono } from "hono";
import { expect, it } from "vitest";
import { fakeGithub } from "../adapters/src/github";
import { adminRoutes } from "../api/src/admin/overview";
import type { Ctx } from "../api/src/app";
import { makeApp } from "../api/src/testkit";

const repo = "stockpilot-hq/stockpilot";
const read = async (bot: ReturnType<typeof fakeGithub> | undefined) => {
  const t = await makeApp();
  const ctx = {
    d1: t.db,
    env: t.env,
    now: () => new Date("2026-11-28T04:00:00Z"),
    guard: { person: async (_c: unknown, next: () => Promise<void>) => next() },
  } as unknown as Ctx;
  const app = new Hono();
  app.route(
    "/",
    adminRoutes(ctx, () => bot),
  );
  const r = await app.request("/api/admin");
  return ((await r.json()) as { needs_you: { kind: string; text: string; url?: string }[] })
    .needs_you;
};

it("LO279 a waiting prototype shows in Needs you with its link", async () => {
  const gh = fakeGithub();
  await gh.openIssue({ repo, title: "Funds screen", body: "", labels: ["prototype-waiting"] });
  await gh.openIssue({ repo, title: "Other", body: "", labels: [] });
  const protos = (await read(gh)).filter((n) => n.kind === "prototype");
  expect(protos).toHaveLength(1);
  expect(protos[0]?.text).toContain("Funds screen");
  expect(protos[0]?.url).toBe(`https://github.com/${repo}/issues/1`);
});

it("LO279 no bot, or a GitHub failure, leaves the rest of Needs you intact", async () => {
  expect((await read(undefined)).filter((n) => n.kind === "prototype")).toEqual([]);
  const gh = fakeGithub();
  gh.openIssuesWithLabel = async () => {
    throw new Error("down");
  };
  expect((await read(gh)).filter((n) => n.kind === "prototype")).toEqual([]);
});
