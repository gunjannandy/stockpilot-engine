// The secrets list: every secret the system holds (names only, never values). The test C-127-1
// keeps it equal to the `secrets:` block of config/stockpilot.yaml.
export const SECRET_NAMES = [
  "VAULT_PASSWORD",
  "CLAUDE_CODE_OAUTH_TOKEN",
  "GOOGLE_BRIDGE_URL",
  "GOOGLE_BRIDGE_KEY",
  "CLOUDFLARE_ACCOUNT_ID",
  "OWNER_PAN",
  "KITE_API_KEY",
  "KITE_API_SECRET",
  "SP_VM_KEY",
] as const;
export const WARN_DAYS = 30;
