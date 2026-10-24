"""Append newly discovered keys to the PO and to the key catalog.

The game translates a few data fields that the first extraction pass missed
(`Observation` for astrology text, `CompletedDescription`, `UnlockText`,
`ResistanceName` ...). Those strings never had a PO entry, which is why they still
show up in English in game.

Two files feed this script:
    extracted/missing_src.tsv   idx <TAB> field <TAB> source text
    extracted/missing_zh.tsv    idx <TAB> chinese

The source text is stored the way the PO wants it: newlines as the two characters
backslash+n (gettext decodes them back to a real newline, which is what the game
looks up at runtime).

Usage
-----
    python append_po_entries.py --dry-run
    python append_po_entries.py --deploy-to <gameDataDir>
"""

import argparse
import io
import os
import shutil
import sys


def read_tsv(path, ncols):
    rows = {}
    for raw in io.open(path, encoding="utf-8-sig").read().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        cells = raw.split("\t")
        if len(cells) < ncols:
            continue
        rows[cells[0].strip()] = cells
    return rows


def po_escape(text):
    # Only quotes need escaping: the writer keeps backslashes as typed, which is
    # the same convention the rest of this PO uses.
    return text.replace('"', '\\"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--catalog", default="extracted/all_keys.txt")
    ap.add_argument("--src", default="extracted/missing_src.tsv")
    ap.add_argument("--zh", default="extracted/missing_zh.tsv")
    ap.add_argument("--deploy-to", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = read_tsv(args.src, 3)
    zh = read_tsv(args.zh, 2)

    existing = set()
    for line in io.open(args.po, encoding="utf-8").read().splitlines():
        if line.startswith('msgid "') and line != 'msgid ""':
            existing.add(line[7:-1].replace('\\"', '"').replace("\\\\", "\\"))

    added, skipped = [], []
    for idx, cells in src.items():
        key = cells[2]
        if not zh.get(idx) or not zh[idx][1].strip():
            skipped.append((idx, "no translation"))
            continue
        if key.replace('\\"', '"').replace("\\\\", "\\") in existing:
            skipped.append((idx, "already present"))
            continue
        added.append((key, zh[idx][1]))

    print("待追加条目:", len(added), "| 跳过:", len(skipped))
    for idx, why in skipped[:8]:
        print("   skip", idx, why)

    if not added:
        print("nothing to add")
        return 0

    if args.dry_run:
        for key, value in added[:10]:
            print("  %-46s -> %s" % (key[:46], value[:34]))
        print("dry run -- nothing written")
        return 0

    with io.open(args.po, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n")
        for key, value in added:
            f.write('msgid "%s"\n' % po_escape(key))
            f.write('msgstr "%s"\n' % po_escape(value))
            f.write("\n")
    print("appended to", args.po)

    with io.open(args.catalog, "a", encoding="utf-8", newline="\n") as f:
        for key, _ in added:
            f.write(key + "\n")
    print("appended to", args.catalog)

    if args.deploy_to:
        target = os.path.join(args.deploy_to, "zh_CN.po")
        shutil.copyfile(args.po, target)
        print("deployed to", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
