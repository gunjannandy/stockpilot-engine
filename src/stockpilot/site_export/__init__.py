"""Lane A, the site's data contract: everything already collected, written as lazily loaded JSON under `site/data/`.
The contract with every field and an example is `schemas/site-contract.md`; a test keeps it equal to the output."""
from stockpilot.site_export.calls import annotate, sell_kind, since, unusual   # noqa: F401
from stockpilot.site_export.io import write_json                               # noqa: F401
