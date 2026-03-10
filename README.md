# smashelito-trader

Converts the **Smashelito ES Daily Plan** newsletter levels to **SPX** using the live fair value from [indexarb.com](https://www.indexarb.com/).

## Setup

No installation required — Python 3 stdlib only.

```
smashelito-trader/
├── posts/       ← downloaded Smashelito posts (markdown)
├── analyzer.py  ← main script
└── README.md
```

## Download Posts

```bash
cd /path/to/substack-save
python3 -m substack_save.cli newsletter.smashelito.com /path/to/smashelito-trader/posts --limit 10 --skip-existing
```

## Analyze

```bash
cd smashelito-trader

# Analyze the most recent post (auto-fetches fair value)
python3 analyzer.py

# Analyze a specific file
python3 analyzer.py ./posts/03-09-2026-es-daily-plan-march-10-2026.md

# Override fair value
python3 analyzer.py --offset 5.59

# Raw ES levels (no conversion)
python3 analyzer.py --offset 0
```

## Sample Output

```
Using: 03-09-2026-es-daily-plan-march-10-2026.md
Fetching fair value from indexarb.com... 5.59 ✓

============================================
  SPX TRADING PLAN — March 10, 2026
  (ES Fair Value: 5.59)
============================================

  PIVOT (Smashlevel):  6772

  BULL SCENARIO (hold above 6772):
    UT1 → 6813
    UT2 → 6844
    FUT → 6874   ← do not chase longs above here

  BEAR SCENARIO (fail 6772):
    DT1 → 6735
    FDT → 6694   ← do not chase shorts below here

  VIX CONFIRMATION:
    Strength confirmed: VIX < 23.12
    Weakness confirmed: VIX > 27.88

  RULE: Non-cooperative VIX = possible reversal setup.
============================================
```
