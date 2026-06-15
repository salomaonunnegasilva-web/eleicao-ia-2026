from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_sources.tse_client import SNAPSHOT_PATH, fetch_live_calendar


def main() -> int:
    payload = fetch_live_calendar(year=2026)
    existing_checksum = None
    if SNAPSHOT_PATH.exists():
        try:
            existing_checksum = json.loads(
                SNAPSHOT_PATH.read_text(encoding="utf-8")
            ).get("checksum")
        except (OSError, json.JSONDecodeError):
            existing_checksum = None

    if existing_checksum == payload["checksum"]:
        print("Official TSE calendar snapshot is already current.")
        return 0

    snapshot = dict(payload)
    snapshot["live_data"] = False
    snapshot["snapshot_note"] = (
        "Versioned fallback generated from the official TSE calendar page."
    )
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Updated {SNAPSHOT_PATH.relative_to(PROJECT_ROOT)} "
        f"with {len(snapshot['entries'])} entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
