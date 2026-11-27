// The tracker email: 30 days ahead, once per expiry, to every person, in plain English.
import { expect, it } from "vitest";
import { makeApp } from "../testkit";
import { runSecretsDuty } from "./duty";

const PEOPLE = JSON.stringify({ owner: "a@example.test", father: "b@example.test" });
const bridge = () => {
  const calls: URL[] = [];
  const fetch = (async (u: string) => {
    calls.push(new URL(u));
    return new Response(JSON.stringify({ ok: true }));
  }) as unknown as typeof globalThis.fetch;
  return { calls, fetch };
};

it("the email page names the secrets inside the window and how many days are left", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  await t.signed("POST", "/api/secrets", { name: "SP_VM_KEY", expires_on: "2026-12-20" });
  const res = await t.withSecret("/api/email/secrets");
  expect(res.status).toBe(200);
  const html = await res.text();
  expect(html).toContain("SP_VM_KEY");
  expect(html).toContain("22 days");
  expect(html).not.toContain("OWNER_PAN");
});

it("the duty emails each person once, then marks the secret as emailed", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  await t.signed("POST", "/api/secrets", { name: "SP_VM_KEY", expires_on: "2026-12-20" });
  const core = {
    d1: t.db,
    now: () => new Date("2026-11-28T10:00:00+05:30"),
    version: "v1",
    env: {
      ...t.env,
      SP_PEOPLE: PEOPLE,
      GOOGLE_BRIDGE_URL: "https://bridge.example.test/exec",
      GOOGLE_BRIDGE_KEY: "bridge-key-0123456789",
    },
  };
  const b = bridge();
  expect(await runSecretsDuty(core, b.fetch)).toContain("emailed 1");
  expect(b.calls.map((c) => c.searchParams.get("to")).sort()).toEqual([
    "a@example.test",
    "b@example.test",
  ]);
  expect(b.calls[0]?.searchParams.get("op")).toBe("send");
  expect(b.calls[0]?.searchParams.get("path")).toBe("/api/email/secrets");
  // second run: nothing due any more
  const again = bridge();
  expect(await runSecretsDuty(core, again.fetch)).toContain("nothing due");
  expect(again.calls).toHaveLength(0);
});

it("a failed send leaves the secret due so the next run tries again", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  await t.signed("POST", "/api/secrets", { name: "SP_VM_KEY", expires_on: "2026-12-20" });
  const core = {
    d1: t.db,
    now: () => new Date("2026-11-28T10:00:00+05:30"),
    version: "v1",
    env: {
      ...t.env,
      SP_PEOPLE: PEOPLE,
      GOOGLE_BRIDGE_URL: "https://bridge.example.test/exec",
      GOOGLE_BRIDGE_KEY: "bridge-key-0123456789",
    },
  };
  const down = (async () => new Response("no", { status: 500 })) as unknown as typeof fetch;
  expect(await runSecretsDuty(core, down)).toContain("not sent");
  const ok = bridge();
  expect(await runSecretsDuty(core, ok.fetch)).toContain("emailed 1");
});

it("the email page also opens for the header the live bridge sends (x-health-key)", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  const { HEALTH } = await import("../testkit");
  const ok = await t.app.request("/api/email/secrets", { headers: { "x-health-key": HEALTH } });
  expect(ok.status).toBe(200);
  const bad = await t.app.request("/api/email/secrets", {
    headers: { "x-health-key": "x".repeat(24) },
  });
  expect(bad.status).toBe(401);
});
