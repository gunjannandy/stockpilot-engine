import { loginBase } from "../../lib/kite.js";

export const onRequestGet = ({ env }) =>
  Response.redirect(`${loginBase(env)}/connect/login?v=3&api_key=${encodeURIComponent(env.KITE_API_KEY)}`, 302);
