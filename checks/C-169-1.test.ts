// C-169-1: watcher issues are opened by stockpilot-bot: the real bot client, with the App's token, in the private repo.
import { expect, it } from "vitest";
import { githubBot } from "../adapters/src/github";
import { opsApp } from "../api/src/watcher/testkit";
import { watch } from "../api/src/watcher/watcher";

it("C-169-1 the watcher opens its issue through the bot client in the private repo", async () => {
  const t = await opsApp();
  await t.heartbeat("job.ping", false, "boom");
  await watch(t.core(), t.github);
  expect(t.github.issues[0]?.repo).toBe("stockpilot-hq/stockpilot");
  expect(t.github.issues[0]?.labels).toContain("watcher");

  // The bot client authenticates as the App's installation (never a personal token) and posts to /issues.
  const pem = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign"],
  );
  const der = new Uint8Array(
    (await crypto.subtle.exportKey("pkcs8", (pem as CryptoKeyPair).privateKey)) as ArrayBuffer,
  );
  const b64 = btoa(String.fromCharCode(...der));
  const calls: { url: string; auth: string }[] = [];
  const fake = (async (url: string, init: RequestInit) => {
    calls.push({ url, auth: String((init.headers as Record<string, string>).authorization) });
    return url.includes("access_tokens")
      ? Response.json({ token: "inst-token" })
      : Response.json({ number: 7 });
  }) as unknown as typeof fetch;
  const bot = githubBot({
    appId: "1",
    installationId: "2",
    privateKey: `-----BEGIN PRIVATE KEY-----\n${b64}\n-----END PRIVATE KEY-----`,
    fetch: fake,
  });
  await watch(t.core(), bot, [{ subject: "x", what: "x is red" }]);
  expect(calls.at(-1)?.url).toContain("/repos/stockpilot-hq/stockpilot/issues");
  expect(calls.at(-1)?.auth).toBe("Bearer inst-token");
});
