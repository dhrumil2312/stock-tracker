"""Stock Movement Explainer API."""

from __future__ import annotations

import sys
from pathlib import Path

# Pipeline and API share `db/` at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
_repo_root = str(REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
