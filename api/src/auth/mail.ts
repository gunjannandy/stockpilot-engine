// The link email goes through the mail adapter (the Apps Script's send endpoint). True only when it sent.
// The address and token are never logged.
import { mailerFromEnv } from "../../../adapters/src/mail";
import type { AuthEnv } from "./lib";

export async function sendLink(
  env: AuthEnv,
  to: string,
  token: string,
  base?: string,
): Promise<boolean> {
  const mailer = mailerFromEnv(env);
  return mailer ? mailer.sendSigninLink(to, token, base) : false;
}
