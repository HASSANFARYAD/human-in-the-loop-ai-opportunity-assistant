from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCAL_TMP = ROOT / ".cache" / "pytest-tmp"
LOCAL_TMP.mkdir(parents=True, exist_ok=True)
for name in ("TMP", "TEMP", "TMPDIR"):
    os.environ[name] = str(LOCAL_TMP)
tempfile.tempdir = str(LOCAL_TMP)
