// `tsx tools/migrate/core/cli.ts --from <export dir> --to <https://v3 address>`; INGEST_HMAC_KEY in the environment.
// Prints the report (counts and checksums, never rows) and exits 1 on any problem. Rerunning changes nothing.
import { datasets } from "../../../contract/src/datasets";
import { migrationDatasets } from "../../../contract/src/migrate/migrate";
import { discoverMaps } from "./discover";
import { ingestSink, jsonDirSource } from "./io";
import { migrate } from "./run";

const arg = (n: string) => process.argv[process.argv.indexOf(`--${n}`) + 1];
const from = arg("from");
const to = arg("to");
const key = process.env.INGEST_HMAC_KEY;
if (!from || !to || !key) {
  console.error("usage: INGEST_HMAC_KEY=... tsx tools/migrate/core/cli.ts --from <dir> --to <url>");
  process.exit(2);
}
const report = await migrate({
  source: jsonDirSource(from),
  sink: ingestSink({
    baseUrl: to.replace(/\/$/, ""),
    hmacKey: key,
    datasets: { ...datasets, ...migrationDatasets },
  }),
  maps: await discoverMaps(),
});
console.log(JSON.stringify(report, null, 1));
process.exit(report.ok ? 0 : 1);
