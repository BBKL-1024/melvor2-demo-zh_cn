"""Apply a list of corrections to the PO, line by line, and optionally deploy it.

Every fix is explicit: nothing is fuzzy-matched, nothing is re-generated. The PO is
only touched at the `msgstr` line that belongs to the listed `msgid`, so a fix can
never reflow a neighbour, lose a placeholder or drop an escape.

Fix file format (tab separated, `#` starts a comment):

  2 columns   msgid <TAB> new msgstr
              exact entry, the only safe way to change a whole sentence

  3 columns   msgid-substring <TAB> old <TAB> new
              substring swap, but only inside entries whose msgid contains the
              first column -- used to unify one term across a family of names
              without hunting them down one by one

Usage
-----
    python apply_fixes.py fixes_v1.tsv
    python apply_fixes.py fixes_v1.tsv --po path/to.po --deploy
    python apply_fixes.py fixes_v1.tsv --dry-run
"""

import argparse
import io
import os
import shutil
import sys


def unpo(s):
    return s.replace('\\"', '"').replace("\\\\", "\\")


def po_escape(s):
    # Mirrors what the original generator wrote: quotes escaped, backslashes left
    # alone (keys really do contain the two characters '\' + 'n').
    return s.replace('"', '\\"')


def load_rules(path):
    exact = {}
    swaps = []
    for raw in io.open(path, encoding="utf-8-sig").read().splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) == 2:
            exact[cells[0]] = cells[1]
        elif len(cells) == 3:
            swaps.append((cells[0], cells[1], cells[2]))
        else:
            print("WARN bad rule line:", raw[:70])
    return exact, swaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rules")
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--deploy-to", default="",
                    help="also copy the result here (the game data dir)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    exact, swaps = load_rules(args.rules)
    lines = io.open(args.po, encoding="utf-8").read().splitlines(True)

    # index every msgid -> the line number of its msgstr
    index = {}
    for i, line in enumerate(lines):
        if line.startswith('msgid "') and line.rstrip("\n") != 'msgid ""':
            if i + 1 < len(lines) and lines[i + 1].startswith('msgstr "'):
                index[unpo(line[7:-2] if line.endswith("\n") else line[7:-1])] = i + 1

    applied, missed, swapped = [], [], []

    for key, value in exact.items():
        pos = index.get(key)
        if pos is None:
            missed.append(key)
            continue
        old = lines[pos]
        lines[pos] = 'msgstr "%s"\n' % po_escape(value)
        applied.append((key, old.strip()[:50], value))

    for scope, old_text, new_text in swaps:
        for key, pos in index.items():
            if scope not in key:
                continue
            line = lines[pos]
            body = line.strip()
            if not body.startswith('msgstr "'):
                continue
            current = unpo(body[8:-1])
            if old_text not in current:
                continue
            lines[pos] = 'msgstr "%s"\n' % po_escape(current.replace(old_text, new_text))
            swapped.append((key, old_text + " -> " + new_text))

    print("explicit fixes applied :", len(applied))
    for key, old, new in applied[:20]:
        print("  %-40s %s => %s" % (key[:40], old, new))
    print("substring swaps        :", len(swapped))
    for key, change in swapped[:20]:
        print("  %-40s %s" % (key[:40], change))
    if missed:
        print("NOT FOUND in po (%d):" % len(missed))
        for key in missed[:10]:
            print("  ?", key[:70])

    if not applied and not swapped:
        print("nothing changed")
        return 1

    if args.dry_run:
        print("dry run -- file not written")
        return 0

    io.open(args.po, "w", encoding="utf-8", newline="\n").write("".join(lines))
    print("wrote", args.po)

    if args.deploy_to:
        target = os.path.join(args.deploy_to, "zh_CN.po")
        shutil.copyfile(args.po, target)
        print("deployed to", target)
        print("restart the game for the change to show up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
