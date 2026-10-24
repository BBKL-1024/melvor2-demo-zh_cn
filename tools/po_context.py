"""Build a per-key context map for the Melvor2 localisation keys.

WHY
---
The PO file is keyed by the English source string and carries no msgctxt, so one
English word can only ever have one translation. That is fine for "Mining" and
hopeless for "String" (a rope-like material vs a bow part) or "Tier"/"Charge".

The data pack embedded in Melvor2.exe stores every localised field next to the
object that owns it, e.g.

    {"Id": "String", "Type": "Material", "DisplayName": "String", ...}

so the owner's Id/Type/Category is recoverable even though the PO has no context.
This script harvests that neighbourhood and writes context.json:

    { "String": [ {"id": "String", "type": "Material", "category": "..."} , ... ] }

Usage:  python po_context.py [--exe Melvor2.exe] [--out context.json]
"""

import argparse
import io
import json
import os
import re
import sys

FIELDS = [
    "DisplayName",
    "Singular",
    "Plural",
    "Description",
    "DialogueText",
    "TemplateString",
]

# Fields that identify the owner of a localised string, nearest-first.
OWNER_FIELDS = ["Id", "Type", "Category", "Skill", "Name", "Tier", "Slot"]

FIELD_RE = re.compile(rb'"(' + b"|".join(f.encode() for f in FIELDS) + rb')": "((?:[^"\\]|\\.)*)"')
OWNER_RE = {
    name: re.compile(rb'"' + name.encode() + rb'": "((?:[^"\\]|\\.)*)"')
    for name in OWNER_FIELDS
}

# How far back to look for the owning object. Data-pack objects are compact, so
# 2500 bytes covers a nested item definition with room to spare, while staying
# short enough not to jump into the previous object.
LOOKBACK = 2500


def decode(raw):
    try:
        return json.loads(b'"' + raw + b'"')
    except Exception:
        return None


def nearest_owner(window):
    """Return the closest owner field values found in `window` (bytes)."""
    best = {}
    for name, pattern in OWNER_RE.items():
        last = None
        for m in pattern.finditer(window):
            last = m  # keep the match closest to the localised field
        if last is not None:
            value = decode(last.group(1))
            if value:
                best[name] = value
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="Melvor2.exe")
    ap.add_argument("--out", default="extracted/context.json")
    ap.add_argument("--probe", action="append", default=[],
                    help="print the data-pack context of these strings too")
    args = ap.parse_args()

    if not os.path.exists(args.exe):
        print("ERROR: %s not found (run from the game root)" % args.exe)
        return 2

    print("reading", args.exe, "...")
    data = open(args.exe, "rb").read()
    print("size: %.1f MB" % (len(data) / 1048576.0))

    context = {}
    hits = 0

    for m in FIELD_RE.finditer(data):
        value = decode(m.group(2))
        if not value or not value.strip():
            continue
        if not re.search(r"[A-Za-z]", value):
            continue

        start = max(0, m.start() - LOOKBACK)
        owner = nearest_owner(data[start:m.start()])

        entry = {"field": m.group(1).decode()}
        entry.update(owner)

        bucket = context.setdefault(value, [])
        if entry not in bucket:
            bucket.append(entry)
        hits += 1

    all_keys = set()
    keys_path = "extracted/all_keys.txt"
    if os.path.exists(keys_path):
        all_keys = set(
            io.open(keys_path, encoding="utf-8-sig").read().splitlines()
        )

    kept = {k: v for k, v in context.items() if not all_keys or k in all_keys}

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(kept, ensure_ascii=False, indent=1, sort_keys=True))

    multi = sum(1 for v in kept.values() if len({e.get("id") for e in v}) > 1)
    print("field hits   :", hits)
    print("keys mapped  :", len(kept), "of", len(all_keys))
    print("ambiguous    :", multi, "(same text owned by more than one object id)")
    print("wrote", args.out)

    for probe in (args.probe or ["String", "Bowstring", "Tier", "Charge"]):
        if probe in kept:
            print()
            print(repr(probe), "->")
            for e in kept[probe][:6]:
                print("   ", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
