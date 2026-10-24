#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find different English keys that were all translated to the SAME Chinese text.

Why this matters: gettext has no msgctxt here, so key->value is a function, but
nothing stops two unrelated keys from sharing one value. In game that shows up as
two different items / monsters / buildings wearing the same Chinese name, and the
player cannot tell them apart.

Not every shared value is a bug:
  * Coat / Coats            -> same word, plural form
  * Adamant Sword / Swords  -> same word, plural form
  * "..." / "..."           -> punctuation only
Those are filtered out (option --show-forms shows them again).

    python dup_target.py                     # report -> extracted/dup_targets.tsv
    python dup_target.py --min-len 2         # only groups whose Chinese is >= 2 chars
    python dup_target.py --show-forms        # include plural/case-only pairs
    python dup_target.py --top 40            # how many groups to print

Run from the game root directory.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

PO = os.path.join("extracted", "zh_CN.po")
CTX = os.path.join("extracted", "context.json")
OUT = os.path.join("extracted", "dup_targets.tsv")


def parse_po(path):
    """Return list of (msgid, msgstr) in file order. Handles multi-line values."""
    entries = []
    msgid = None
    msgstr = None
    field = None

    def flush():
        if msgid is not None and msgstr is not None:
            entries.append((msgid, msgstr))

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            if line.startswith("msgid "):
                if msgid is not None and msgstr is not None:
                    flush()
                msgid = unquote(line[6:])
                msgstr = None
                field = "id"
            elif line.startswith("msgstr "):
                msgstr = unquote(line[7:])
                field = "str"
            elif line.startswith('"'):
                chunk = unquote(line)
                if field == "id":
                    msgid = (msgid or "") + chunk
                elif field == "str":
                    msgstr = (msgstr or "") + chunk
    if msgid is not None and msgstr is not None:
        flush()
    return entries


def unquote(s):
    s = s.strip()
    if not (len(s) >= 2 and s[0] == '"' and s[-1] == '"'):
        return s
    body = s[1:-1]
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def norm(s):
    return unicodedata.normalize("NFKC", s).strip().lower()


def stems(w):
    """All plausible singular stems of an English word."""
    out = {w}
    if w.endswith("ies") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("ves") and len(w) > 4:
        out.add(w[:-3] + "f")
        out.add(w[:-3] + "fe")
    if w.endswith("es") and len(w) > 3:
        out.add(w[:-2])
    if w.endswith("s") and len(w) > 2:
        out.add(w[:-1])
    return out


def forms_related(a, b):
    """True when two English keys are just case / plural variants of one another."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    if stems(na) & stems(nb):
        return True
    # same words, different order ("Copper Bar" / "Bar Copper") -- treat as related
    if sorted(na.split()) == sorted(nb.split()):
        return True
    # one is the other with spaces removed ("Wall of Blood" / "WallofBlood")
    if na.replace(" ", "") == nb.replace(" ", ""):
        return True
    return False


def noise(s):
    """Punctuation / placeholder-only strings are not real translations."""
    stripped = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)
    stripped = re.sub(r"\{[^}]*\}", "", stripped)
    return len(stripped) == 0


def load_context():
    try:
        with open(CTX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ctx_of(ctx, key):
    """Summarise where a key is used. context.json maps key -> list of field records."""
    if not isinstance(ctx, dict):
        return ""
    info = ctx.get(key)
    if info is None:
        return ""
    if isinstance(info, dict):
        info = [info]
    if not isinstance(info, list):
        return ""

    seen = []
    for rec in info:
        if not isinstance(rec, dict):
            continue
        bits = [rec.get("Type") or rec.get("Category") or "", rec.get("Id") or "", rec.get("field") or ""]
        label = ":".join(b for b in bits if b)
        if label and label not in seen:
            seen.append(label)
    if len(seen) > 3:
        seen = seen[:3] + ["+%d more" % (len(seen) - 3)]
    return "; ".join(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-len", type=int, default=1, help="skip groups whose Chinese is shorter than this")
    ap.add_argument("--show-forms", action="store_true", help="also report case/plural-only pairs")
    ap.add_argument("--top", type=int, default=60, help="how many groups to print")
    args = ap.parse_args()

    if not os.path.isfile(PO):
        sys.exit("missing " + PO + " (run from the game root)")

    entries = parse_po(PO)
    by_target = {}
    for msgid, msgstr in entries:
        if not msgid or not msgstr:
            continue
        if msgid == msgstr:
            continue
        if noise(msgstr):
            continue
        by_target.setdefault(msgstr, []).append(msgid)

    ctx = load_context()
    groups = []
    for target, ids in by_target.items():
        uniq = sorted(set(ids))
        if len(uniq) < 2:
            continue
        if len(re.sub(r"\s", "", target)) < args.min_len:
            continue

        if not args.show_forms:
            # keep the group only if at least one pair is genuinely unrelated
            unrelated = False
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    if not forms_related(uniq[i], uniq[j]):
                        unrelated = True
                        break
                if unrelated:
                    break
            if not unrelated:
                continue

        groups.append((target, uniq))

    # sort: more collisions first, then shorter (short labels hurt most)
    groups.sort(key=lambda g: (-len(g[1]), len(g[0])))

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("chinese\tcount\tenglish_keys\twhere\n")
        for target, ids in groups:
            where = " | ".join(filter(None, (ctx_of(ctx, k) for k in ids)))
            f.write("%s\t%d\t%s\t%s\n" % (target, len(ids), " | ".join(ids), where))

    print("entries parsed : %d" % len(entries))
    print("distinct targets: %d" % len(by_target))
    print("conflict groups : %d  -> %s" % (len(groups), OUT))
    print()

    for target, ids in groups[: args.top]:
        print("[%d] %s" % (len(ids), target))
        for k in ids:
            w = ctx_of(ctx, k)
            print("      <- %s%s" % (k, ("    [" + w + "]") if w else ""))
        print()


if __name__ == "__main__":
    main()
