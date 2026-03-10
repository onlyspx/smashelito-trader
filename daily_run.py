#!/usr/bin/env python3
"""
daily_run.py — Fetch new Smashelito posts, analyze, save JSON, notify Discord.

Usage:
    python3 daily_run.py [--force]

    --force     Re-analyze dates that already have a saved analysis/YYYY-MM-DD.json
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from analyzer import fetch_fair_value, parse_post, es_to_spx

POSTS_DIR = Path(__file__).parent / "posts"
ANALYSIS_DIR = Path(__file__).parent / "analysis"
NEWSLETTER = "newsletter.smashelito.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_posts():
    """Run substack_save to download any new posts."""
    cmd = [
        sys.executable, "-m", "substack_save.cli",
        NEWSLETTER, str(POSTS_DIR), "--skip-existing", "--limit", "5",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[warn] substack_save exited {result.returncode}: {result.stderr.strip()}")
    else:
        print("Posts synced.")


def parse_plan_date(levels: dict) -> str | None:
    """Extract YYYY-MM-DD from post title or published date."""
    title = levels.get("title", "")
    # Title format: "ES Daily Plan | March 10, 2026"
    m = re.search(r"\|\s*(.+)$", title)
    if m:
        date_str = m.group(1).strip()
        try:
            dt = datetime.strptime(date_str, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    published = levels.get("date", "")
    if re.match(r"\d{4}-\d{2}-\d{2}", published):
        return published[:10]
    return None


def build_spx_levels(es_levels: dict, fv: float) -> dict:
    spx = {}
    for key, val in es_levels.items():
        if isinstance(val, int):
            spx[key] = round(val - fv, 2)
    return spx


def save_analysis(plan_date: str, levels: dict, fv: float) -> Path:
    ANALYSIS_DIR.mkdir(exist_ok=True)
    es_levels = {k: v for k, v in levels.items() if k not in ("title", "date")}
    spx_levels = build_spx_levels(es_levels, fv)
    payload = {
        "title": levels.get("title", ""),
        "plan_for_date": plan_date,
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "fair_value": fv,
        "es_levels": es_levels,
        "spx_levels": spx_levels,
    }
    out_path = ANALYSIS_DIR / f"{plan_date}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


# ---------------------------------------------------------------------------
# Discord notification
# ---------------------------------------------------------------------------

def post_discord(payload: dict, webhook_url: str):
    """Send a formatted embed to a Discord webhook."""
    fv = payload["fair_value"]
    plan_date = payload["plan_for_date"]
    try:
        dt = datetime.strptime(plan_date, "%Y-%m-%d")
        readable_date = dt.strftime("%B %-d, %Y")
    except Exception:
        readable_date = plan_date

    es = payload["es_levels"]
    spx = payload["spx_levels"]

    lines = [f"Fair Value: {fv}\n"]
    level_order = ["smashlevel", "ut1", "ut2", "fut", "dt1", "dt2", "fdt"]
    label_map = {
        "smashlevel": "Smashlevel",
        "ut1": "UT1", "ut2": "UT2", "fut": "FUT",
        "dt1": "DT1", "dt2": "DT2", "fdt": "FDT",
    }
    for key in level_order:
        if key in es:
            label = label_map.get(key, key.upper())
            lines.append(f"{label:<12}{es[key]} → {spx.get(key, '?')}")

    description = "\n".join(lines)

    embed = {
        "title": f"ES Daily Plan — {readable_date}",
        "description": f"```\n{description}\n```",
        "color": 3447003,  # blue
    }
    body = json.dumps({"embeds": [embed]}).encode()
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status not in (200, 204):
            print(f"[warn] Discord returned HTTP {resp.status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Daily fetch, analyze, and notify.")
    parser.add_argument("--force", action="store_true",
                        help="Re-analyze even if analysis JSON already exists.")
    args = parser.parse_args()

    # 1. Fetch new posts
    fetch_posts()

    # 2. Find all markdown posts
    md_files = sorted(glob.glob(str(POSTS_DIR / "*.md")))
    if not md_files:
        print("No posts found.")
        return

    # 3. Determine which need analysis
    ANALYSIS_DIR.mkdir(exist_ok=True)
    to_analyze = []
    for md_path in md_files:
        text = Path(md_path).read_text(encoding="utf-8")
        levels = parse_post(text)
        plan_date = parse_plan_date(levels)
        if plan_date is None:
            continue
        json_path = ANALYSIS_DIR / f"{plan_date}.json"
        if json_path.exists() and not args.force:
            continue
        to_analyze.append((md_path, levels, plan_date))

    if not to_analyze:
        print("No new posts to analyze.")
        return

    # 4. Fetch fair value once for all posts
    print("Fetching fair value from indexarb.com...", end=" ", flush=True)
    fv = fetch_fair_value()
    if fv is not None:
        print(f"{fv} ✓")
    else:
        fv = 6.0
        print(f"[failed] — using default {fv}")

    # 5. Analyze and save
    saved = []
    for md_path, levels, plan_date in to_analyze:
        out_path = save_analysis(plan_date, levels, fv)
        print(f"Saved: {out_path}")
        saved.append(out_path)

    # 6. Post to Discord (most recent date only)
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook_url and saved:
        # Use the latest saved analysis for the notification
        latest_path = sorted(saved)[-1]
        payload = json.loads(latest_path.read_text())
        try:
            post_discord(payload, webhook_url)
            print(f"Discord notified for {payload['plan_for_date']}.")
        except Exception as e:
            print(f"[warn] Discord notification failed: {e}")
    elif not webhook_url:
        print("[info] DISCORD_WEBHOOK_URL not set — skipping notification.")

    print(f"\nDone. {len(saved)} file(s) written.")


if __name__ == "__main__":
    main()
