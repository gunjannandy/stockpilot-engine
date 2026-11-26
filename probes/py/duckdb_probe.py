"""Probe 1: can DuckDB read a Parquet file through a GitHub release redirect by HTTP range requests?

probe(url, sql) -> {"ok", "value", "seconds", "bytes_fetched", "error"}. The sql names the file as table `t`.
Fallback if this fails: download the file to disk first, then query the local copy.
"""
import sys, time, json
import duckdb


def probe(url, sql):
    t0 = time.time()
    try:
        con = duckdb.connect()
        try:
            con.sql("INSTALL httpfs; LOAD httpfs")
        except Exception:
            pass  # a plain http:// url works without it on some builds; https needs it
        con.sql("SET enable_http_metadata_cache=false")
        con.sql(f"CREATE VIEW t AS SELECT * FROM read_parquet('{url}')")
        value = con.sql(sql).fetchone()[0]
        fetched = None
        try:
            fetched = con.sql("SELECT total_bytes_read FROM duckdb_http_stats()").fetchone()[0]
        except Exception:
            pass
        return {"ok": True, "value": value, "seconds": round(time.time() - t0, 2), "bytes_fetched": fetched, "error": None}
    except Exception as e:  # report, never raise: the point is to record the result
        return {"ok": False, "value": None, "seconds": round(time.time() - t0, 2), "bytes_fetched": None, "error": str(e)[:300]}


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "SELECT count(*) FROM t")))
