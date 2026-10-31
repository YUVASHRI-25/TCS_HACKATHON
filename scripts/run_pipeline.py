"""make pipeline -> runs the TRACE pipeline end to end."""

import json
import sys
from pathlib import Path

# backend/ must precede the stdlib on sys.path: the package is named `trace` (stdlib has a `trace` module).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from trace.application.run_pipeline import MappingNotConfigured, run  # noqa: E402
from trace.infrastructure.logging import configure  # noqa: E402

if __name__ == "__main__":
    configure()
    try:
        print(json.dumps(run(), indent=2, default=str))
    except MappingNotConfigured as e:
        print(f"Pipeline not run: {e}", file=sys.stderr)
        sys.exit(2)
