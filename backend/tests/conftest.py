import sys
from pathlib import Path

# The package is named `trace`, which collides with the stdlib module; put backend/ first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.pop("trace", None)
