"""Check that derived names keep the same Chinese root as the thing they derive from.

四类派生关系，中文必须共享词根，否则玩家会以为是两样东西：

    X Seed(s) ↔ X / X Herb(s)      种子 ↔ 植物
    X Log(s)  ↔ X Tree             原木 ↔ 树
    X Heart / Fang / Horn … ↔ X    掉落物 ↔ 怪物
    X(s)      ↔ X                  单复数（中文没有复数，两条应当同译）

    python derived_check.py
    python derived_check.py --po extracted/zh_CN.po
"""

import argparse
import io
import re
import sys

DROP_SUFFIXES = (
    "Heart", "Hearts", "Fang", "Fangs", "Bone", "Bones", "Scale", "Scales",
    "Skin", "Skins", "Eye", "Eyes", "Claw", "Claws", "Horn", "Horns",
    "Feather", "Feathers", "Wing", "Wings",
)

SEED_RE = re.compile(r"^(.+?)( Herb)? Seeds?$")
LOG_RE = re.compile(r"^(.+) Logs?$")

NAME_ONLY = re.compile(r"^[A-Z][A-Za-z' ]+$")


def unpo(s):
    return s.replace('\\"', '"').replace("\\\\", "\\")


def parse_po(path):
    po, msgid = {}, None
    for line in io.open(path, encoding="utf-8").read().splitlines():
        s = line.rstrip()
        if s.startswith('msgid "'):
            if s == 'msgid ""':
                msgid = None
                continue
            msgid = unpo(s[7:-1])
        elif s.startswith('msgstr "') and msgid is not None:
            po[msgid] = unpo(s[8:-1])
            msgid = None
    return po


def shared_prefix(a, b):
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


def check_seeds(po):
    bad = []
    for key, zh in po.items():
        m = SEED_RE.match(key)
        if not m or not zh:
            continue
        base = m.group(1)
        roots = [po[b] for b in (base + " Herb", base + " Herbs", base) if po.get(b)]
        if not roots:
            continue
        if not any(zh == r + "种子" or zh.startswith(r) for r in roots):
            bad.append((key, zh, roots[0]))
    return bad


def check_logs(po):
    bad = []
    for key, zh in po.items():
        m = LOG_RE.match(key)
        if not m or not zh:
            continue
        tree = po.get(m.group(1) + " Tree")
        if not tree:
            continue                    # Bonfire/Event/Completion Log 之类不是木头
        if shared_prefix(zh, tree) < 1:
            bad.append((key, zh, tree))
    return bad


def check_drops(po):
    bad = []
    for key, zh in po.items():
        if not zh or not NAME_ONLY.match(key):
            continue
        words = key.split()
        if len(words) < 2 or words[-1] not in DROP_SUFFIXES:
            continue
        base = " ".join(words[:-1])
        if base not in po or not po[base]:
            continue
        if shared_prefix(zh, po[base]) < 1:
            bad.append((key, zh, po[base]))
    return bad


def check_plurals(po):
    bad = []
    for key, zh in po.items():
        if not zh or not key.endswith("s") or not NAME_ONLY.match(key):
            continue
        single = key[:-1]
        if single in po and po[single] and po[single] != zh:
            bad.append((single, po[single], key, zh))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    args = ap.parse_args()

    po = parse_po(args.po)
    total = 0

    for title, rows, fmt in (
        ("种子 ↔ 植物", check_seeds(po), lambda r: "%-28s %-16s | 植物: %s" % r),
        ("原木 ↔ 树", check_logs(po), lambda r: "%-28s %-16s | 树:   %s" % r),
        ("掉落物 ↔ 怪物", check_drops(po), lambda r: "%-28s %-16s | 怪物: %s" % r),
    ):
        print("=== %s : %d ===" % (title, len(rows)))
        for r in rows:
            print("   " + fmt(r))
        total += len(rows)

    plurals = check_plurals(po)
    print("=== 单复数 : %d ===" % len(plurals))
    for single, sv, plural, pv in plurals:
        print("   %-24s=%-14s | %-24s=%s" % (single[:24], sv[:14], plural[:24], pv[:14]))
    total += len(plurals)

    print()
    print("合计", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
