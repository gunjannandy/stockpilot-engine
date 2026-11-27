import { expect, it } from "vitest";
import { appJwt, fakeGithub, githubBot, githubFromEnv } from "./index";

async function pem() {
  const { privateKey } = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  );
  const der = new Uint8Array(await crypto.subtle.exportKey("pkcs8", privateKey));
  const b64 = btoa(String.fromCharCode(...der)).replace(/(.{64})/g, "$1\n");
  return `-----BEGIN PRIVATE KEY-----\n${b64}\n-----END PRIVATE KEY-----`;
}

it("the App JWT has three parts and names the App", async () => {
  const jwt = await appJwt("123", await pem(), new Date("2026-11-27T05:00:00Z"));
  const [h, p, s] = jwt.split(".");
  expect(JSON.parse(atob(h as string))).toEqual({ alg: ["RS", "256"].join(""), typ: "JWT" });
  expect(JSON.parse(atob(p as string)).iss).toBe("123");
  expect((s as string).length).toBeGreaterThan(100);
});

it("the bot swaps the App key for an installation token once, then starts a workflow with it", async () => {
  const calls: { url: string; method: string; auth: string; body: unknown }[] = [];
  const fake: typeof fetch = async (url, init) => {
    const h = init?.headers as Record<string, string>;
    calls.push({
      url: String(url),
      method: init?.method ?? "GET",
      auth: h.authorization ?? "",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    if (String(url).endsWith("/access_tokens"))
      return Response.json({ token: "inst-token" }, { status: 201 });
    return new Response(null, { status: 204 });
  };
  const bot = githubBot({
    appId: "1",
    installationId: "9",
    privateKey: await pem(),
    fetch: fake,
    now: () => new Date("2026-11-27T05:00:00Z"),
  });
  await bot.dispatchWorkflow({
    repo: "o/r",
    workflow: "calendar.yml",
    ref: "main",
    inputs: { kind: "calendar" },
  });
  await bot.dispatchWorkflow({
    repo: "o/r",
    workflow: "calendar.yml",
    ref: "main",
    inputs: { kind: "calendar" },
  });
  expect(calls.filter((c) => c.url.endsWith("/access_tokens"))).toHaveLength(1);
  const d = calls.filter((c) => c.url.includes("/dispatches"));
  expect(d).toHaveLength(2);
  expect(d[0]).toMatchObject({
    url: "https://api.github.com/repos/o/r/actions/workflows/calendar.yml/dispatches",
    method: "POST",
    auth: "Bearer inst-token",
    body: { ref: "main", inputs: { kind: "calendar" } },
  });
});

it("a refused call throws with the status", async () => {
  const bot = githubBot({
    appId: "1",
    installationId: "9",
    privateKey: await pem(),
    fetch: async () => new Response("no", { status: 403 }),
  });
  await expect(bot.labels({ repo: "o/r", issue: 1 })).rejects.toThrow("403");
});

it("the fake records dispatches, issues, comments and labels", async () => {
  const g = fakeGithub();
  const n = await g.openIssue({ repo: "o/r", title: "t", body: "b", labels: ["x"] });
  await g.comment({ repo: "o/r", issue: n, body: "hi" });
  expect(await g.labels({ repo: "o/r", issue: n })).toEqual(["x"]);
  expect(g.issues[0]?.comments).toEqual(["hi"]);
});

it("no secrets, no bot", () => {
  expect(githubFromEnv({})).toBeUndefined();
});
