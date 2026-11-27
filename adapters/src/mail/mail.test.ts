import { describe, expect, it } from "vitest";
import { bridgeMailer, fakeMailer, mailerFromEnv } from "./index";

describe("mail adapter", () => {
  it("sends op=signin and is true only on ok:true", async () => {
    let seen = "";
    const ok = (async (u: RequestInfo | URL) => {
      seen = String(u);
      return Response.json({ ok: true });
    }) as typeof fetch;
    const m = bridgeMailer({ url: "https://b.example.test/exec", key: "k", fetch: ok });
    expect(await m.sendSigninLink("a@example.test", "tok")).toBe(true);
    const q = new URL(seen).searchParams;
    expect([q.get("op"), q.get("to"), q.get("t"), q.get("key")]).toEqual([
      "signin",
      "a@example.test",
      "tok",
      "k",
    ]);
    const no = (async () => Response.json({ ok: false })) as typeof fetch;
    expect(
      await bridgeMailer({ url: "https://b.example.test/", key: "k", fetch: no }).sendSigninLink(
        "a",
        "t",
      ),
    ).toBe(false);
    const boom = (async () => {
      throw new Error("x");
    }) as typeof fetch;
    expect(
      await bridgeMailer({ url: "https://b.example.test/", key: "k", fetch: boom }).sendSigninLink(
        "a",
        "t",
      ),
    ).toBe(false);
  });
  it("fake records and can fail; env without config gives none", async () => {
    const f = fakeMailer();
    expect(await f.sendSigninLink("a", "t")).toBe(true);
    expect(f.sent).toEqual([{ to: "a", token: "t" }]);
    expect(await fakeMailer({ fail: true }).sendSigninLink("a", "t")).toBe(false);
    expect(mailerFromEnv({})).toBeUndefined();
  });
});
