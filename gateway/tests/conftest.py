"""Make the sibling mmwave-engine importable in this workspace."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3] / "mmwave-engine"
if (ENGINE / "mmwave_engine" / "__init__.py").is_file():
    sys.path.insert(0, str(ENGINE))
