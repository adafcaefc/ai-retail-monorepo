from __future__ import annotations

import json
import os
from pathlib import Path

import requests


def main() -> int:
    webhook_url = os.getenv("TEAMS_POWER_AUTOMATE_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError(
            "Set TEAMS_POWER_AUTOMATE_WEBHOOK_URL before running this smoke test."
        )

    card_path = Path(__file__).with_name("test_renderer_output.json")
    adaptive_card = json.loads(card_path.read_text(encoding="utf-8"))
    response = requests.post(
        webhook_url,
        json=adaptive_card,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    print(f"Teams status: {response.status_code}")
    return 0 if response.status_code in (200, 201, 202) else 1


if __name__ == "__main__":
    raise SystemExit(main())