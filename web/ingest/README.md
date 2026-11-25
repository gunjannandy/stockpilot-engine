# Ingest Worker

Public jobs write `news_items`, `news_tags` and `quotes` here and nowhere else. Request: `POST` JSON `{table, rows}` with headers `X-SP-Timestamp` (epoch ms, within 5 minutes) and `X-SP-Signature` (hex HMAC-SHA256 of `<timestamp>.<raw body>`, key `INGEST_KEY`). Private tables get 403; a bad key gets 401; at 85,000 rows written today it answers 429 (D1 stops at 100,000).
