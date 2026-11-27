// C-127-1: the tracker lists every secret in the secrets list with its expiry, and flags the due ones.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import { repoRoot } from "../api/migrate/discover";
import { SECRET_NAMES } from "../api/src/secrets/list";
import { makeApp } from "../api/src/testkit";

it("C-127-1 the list matches the config and the tracker flags secrets inside 30 days", async () => {
  const yaml = readFileSync(join(repoRoot, "config/stockpilot.yaml"), "utf8");
  const block = yaml.split("\nsecrets:\n")[1]?.split("\n\n")[0] ?? "";
  const names = [...block.matchAll(/^ {2}([A-Z0-9_]+):/gm)].map((m) => m[1]);
  expect([...SECRET_NAMES].sort()).toEqual(names.sort());

  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  await t.signed("POST", "/api/secrets", { name: "SP_VM_KEY", expires_on: "2026-12-20" });
  await t.signed("POST", "/api/secrets", { name: "OWNER_PAN", expires_on: "2027-06-01" });
  expect((await t.signed("POST", "/api/secrets", { name: "NOPE", expires_on: null })).status).toBe(
    400,
  );
  const get = async () =>
    (await (await t.withSecret("/api/secrets")).json()) as {
      secrets: { name: string; days_left: number | null; due: boolean }[];
    };
  let body = await get();
  expect(body.secrets.map((s) => s.name).sort()).toEqual([...SECRET_NAMES].sort());
  expect(body.secrets.find((s) => s.name === "SP_VM_KEY")).toMatchObject({
    days_left: 22,
    due: true,
  });
  expect(body.secrets.find((s) => s.name === "OWNER_PAN")?.due).toBe(false);
  await t.signed("POST", "/api/secrets", { name: "SP_VM_KEY", notified: true });
  body = await get();
  expect(body.secrets.find((s) => s.name === "SP_VM_KEY")?.due).toBe(false);
  expect((await t.app.request("/api/secrets")).status).toBe(401);
});
