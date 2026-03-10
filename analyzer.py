#!/usr/bin/env python3
"""
analyzer.py — Smashelito ES Daily Plan → SPX Level Extractor

Usage:
    python3 analyzer.py [file.md] [--offset FLOAT]

    file.md     Path to a Smashelito post (default: most recent in posts/)
    --offset    Override fair value (default: fetched live from indexarb.com)
                Use --offset 0 to show raw ES levels with no conversion
"""

import argparse
import re
import sys
import urllib.request
import os
import glob
from pathlib import Path


# ---------------------------------------------------------------------------
# Fair Value Scraper
# ---------------------------------------------------------------------------

def fetch_fair_value() -> float | None:
    """Scrape current ES/SPX fair value premium from indexarb.com.

    The S&P 500 row layout is: Label | SA | ST | FV | BT | BA
    We skip the label cell (matching S&amp;P), skip SA and ST, then capture FV.

    Returns the fair value float, or None on failure.
    """
    url = "https://www.indexarb.com/"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; smashelito-analyzer/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html_bytes = resp.read()
        html_text = html_bytes.decode("utf-8", errors="replace")

        # Match S&P data row (label contains S&amp;P<BR>) → skip actual premium + sell
        # threshold → capture Fair Value
        # Columns: label | actual premium | sell threshold | Fair Value | buy threshold
        match = re.search(
            r'S&amp;P<BR>[\s\S]*?</TD>'    # skip label cell (anchored to data row)
            r'(?:[\s\S]*?</TD>){2}'         # skip actual premium and sell threshold
            r'[\s\S]*?<TD[^>]*>\s*([-]?\d+(?:\.\d+)?)',  # capture Fair Value
            html_text,
            re.IGNORECASE,
        )
        if match:
            return float(match.group(1))

    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Markdown Parser
# ---------------------------------------------------------------------------

def parse_post(text: str) -> dict:
    """Extract title, date, and ES levels from a Smashelito markdown post."""
    levels = {}

    # Title / date from first heading
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    levels["title"] = title_match.group(1).strip() if title_match else "ES Daily Plan"

    # Published date
    date_match = re.search(r"\*\*Published:\*\*\s+(\S+)", text)
    levels["date"] = date_match.group(1) if date_match else ""

    # Smashlevel
    m = re.search(r"\*\*Smashlevel\*\*\s+is\s+\*\*(\d+)\*\*", text)
    if m:
        levels["smashlevel"] = int(m.group(1))

    # UT1
    m = re.search(r"\*\*(\d+)\s*\(UT1\)\*\*", text)
    if m:
        levels["ut1"] = int(m.group(1))

    # UT2
    m = re.search(r"\*\*(\d+)\s*\(UT2\)\*\*", text)
    if m:
        levels["ut2"] = int(m.group(1))

    # FUT
    m = re.search(r"\*\*(\d+)\s*\(FUT\)\*\*", text)
    if m:
        levels["fut"] = int(m.group(1))

    # DT1
    m = re.search(r"\*\*(\d+)\s*\(DT1\)\*\*", text)
    if m:
        levels["dt1"] = int(m.group(1))

    # DT2 (optional)
    m = re.search(r"\*\*(\d+)\s*\(DT2\)\*\*", text)
    if m:
        levels["dt2"] = int(m.group(1))

    # FDT
    m = re.search(r"\*\*(\d+)\s*\(FDT\)\*\*", text)
    if m:
        levels["fdt"] = int(m.group(1))

    # VIX strength (below) — may have trailing space before closing **
    m = re.search(r"VIX below \*\*(\d+\.\d+)\s*\*\*", text)
    if m:
        levels["vix_strength"] = float(m.group(1))

    # VIX weakness (above)
    m = re.search(r"VIX above \*\*(\d+\.\d+)\s*\*\*", text)
    if m:
        levels["vix_weakness"] = float(m.group(1))

    return levels


# ---------------------------------------------------------------------------
# Output Formatter
# ---------------------------------------------------------------------------

def format_date_from_published(published: str) -> str:
    """Convert '2026-03-10' to 'March 10, 2026'."""
    try:
        from datetime import datetime
        dt = datetime.strptime(published, "%Y-%m-%d")
        return dt.strftime("%B %-d, %Y")
    except Exception:
        return published


def es_to_spx(es_level: int, fv: float) -> int:
    return round(es_level - fv)


def print_plan(levels: dict, fv: float):
    raw = fv == 0.0

    # Prefer date from title ("ES Daily Plan | March 10, 2026") as it reflects the plan date
    title = levels.get("title", "")
    m = re.search(r"\|\s*(.+)$", title)
    if m:
        plan_date = m.group(1).strip()
    else:
        plan_date = format_date_from_published(levels.get("date", "")) or title

    fv_label = "raw ES" if raw else f"ES Fair Value: {fv:.2f}"

    print()
    print("=" * 44)
    print(f"  SPX TRADING PLAN — {plan_date}")
    print(f"  ({fv_label})")
    print("=" * 44)

    def conv(es: int) -> str:
        if raw:
            return str(es)
        return str(es_to_spx(es, fv))

    smashlevel = levels.get("smashlevel")
    if smashlevel is None:
        print("\n  [!] Could not parse Smashlevel from post.")
        return

    spx_smashlevel = conv(smashlevel)
    print(f"\n  PIVOT (Smashlevel):  {spx_smashlevel}")

    print(f"\n  BULL SCENARIO (hold above {spx_smashlevel}):")
    if "ut1" in levels:
        print(f"    UT1 → {conv(levels['ut1'])}")
    if "ut2" in levels:
        print(f"    UT2 → {conv(levels['ut2'])}")
    if "fut" in levels:
        print(f"    FUT → {conv(levels['fut'])}   ← do not chase longs above here")

    print(f"\n  BEAR SCENARIO (fail {spx_smashlevel}):")
    if "dt1" in levels:
        print(f"    DT1 → {conv(levels['dt1'])}")
    if "dt2" in levels:
        print(f"    DT2 → {conv(levels['dt2'])}")
    if "fdt" in levels:
        print(f"    FDT → {conv(levels['fdt'])}   ← do not chase shorts below here")

    if "vix_strength" in levels or "vix_weakness" in levels:
        print("\n  VIX CONFIRMATION:")
        if "vix_strength" in levels:
            print(f"    Strength confirmed: VIX < {levels['vix_strength']:.2f}")
        if "vix_weakness" in levels:
            print(f"    Weakness confirmed: VIX > {levels['vix_weakness']:.2f}")

    print("\n  RULE: Non-cooperative VIX = possible reversal setup.")
    print("=" * 44)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_latest_post(posts_dir: str) -> str | None:
    pattern = os.path.join(posts_dir, "*.md")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Smashelito ES Daily Plan levels to SPX."
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a Smashelito markdown post (default: most recent in posts/)",
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=None,
        help="Override fair value offset (default: fetch live). Use 0 for raw ES.",
    )
    args = parser.parse_args()

    # Resolve file
    if args.file:
        post_path = args.file
    else:
        script_dir = Path(__file__).parent
        posts_dir = script_dir / "posts"
        post_path = find_latest_post(str(posts_dir))
        if not post_path:
            print(f"No .md files found in {posts_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Using: {os.path.basename(post_path)}")

    try:
        with open(post_path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"File not found: {post_path}", file=sys.stderr)
        sys.exit(1)

    # Resolve fair value
    if args.offset is not None:
        fv = args.offset
        if fv == 0.0:
            print("Using raw ES levels (no conversion).")
        else:
            print(f"Using override offset: {fv}")
    else:
        print("Fetching fair value from indexarb.com...", end=" ", flush=True)
        fv = fetch_fair_value()
        if fv is not None:
            print(f"{fv} ✓")
        else:
            fv = 6.0
            print(f"[failed] — using default {fv}")

    # Parse and display
    levels = parse_post(text)
    print_plan(levels, fv)


if __name__ == "__main__":
    main()
