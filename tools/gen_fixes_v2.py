"""Round-2 term rulings -> an explicit, auditable fix list.

Nothing here guesses. Each rule is expressed as "inside entries whose msgid
mentions TERM, replace OLD with NEW", and the script expands it into one exact
`msgid -> new msgstr` line per entry. The result can be reviewed line by line and
replayed with apply_fixes.py, which only ever touches the msgstr of a listed msgid.

Run from the game folder:
    python gen_fixes_v2.py --out ../tools/fixes_v2.tsv
"""

import argparse
import collections
import io
import re
import sys

# (scope substring, old text, new text, human reason)
# scope is matched case-sensitively against the msgid.
RULES = [
    ("Wizard", "法师", "巫师", "组合名 82 条已用「巫师」，单词条目是少数派"),
    ("Slayer", "杀手", "杀戮", "技能名统一为「杀戮」"),
    ("Slayer", "屠杀", "杀戮", "「屠杀」仅 3 条"),
    ("Max Hit", "最大命中", "最大伤害", "Max Hit 是伤害上限，命中是另一项"),
    ("max hit", "最大命中", "最大伤害", "同上（小写形式）"),
    ("max hit", "最小命中", "最小伤害", "min hit 是最小伤害"),
    ("Max Hit", "最小命中", "最小伤害", "min hit 是最小伤害"),
    ("maximum hit", "最大命中", "最大伤害", "maximum hit 是 Max Hit 的另一种写法"),
    ("Spirit", "魂灵", "灵魂", "同族条目已用「灵魂盒」"),
    ("Amulet", "护符", "护身符", "40 条用「护身符」"),
    ("Torso", "上衣", "上身", "15 条组合名用「上身」"),
    ("Power Rating", "力量评级", "强度评级", "同词条已用「强度」"),
    ("Major Update", "大型更新", "重大更新", "4 条中 3 条用「重大」"),
    ("Snare", "绊索", "绳套", "7 条用「绳套」"),
    ("Stick", "追踪棒", "追踪杖", "Tracking Stick 同类 3:3，取「杖」"),
    ("Leather Body", "皮革", "皮", "同一套装甲内 硬皮革上身 vs 硬皮靴"),
    ("Leather Bodies", "皮革", "皮", "同上（复数形式）"),
]

# Entries that must be fixed by whole value, because a substring swap inside them
# would produce something ungrammatical (Slayer ranks read as titles, not items).
EXACT = {
    "Apprentice Slayer": "学徒杀戮者",
    "Journeyman Slayer": "熟练杀戮者",
    "Slayer Initiate": "杀戮者入门",
    "Slayer General": "杀戮通用",
    "Slayer General Upgrades": "杀戮通用升级",
    "Observations": "观测",
    "Power": "强度",
}


def read_po(path):
    lines = io.open(path, encoding="utf-8").read().splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('msgid "') and line != 'msgid ""':
            key = line[7:-1].replace('\\"', '"').replace("\\\\", "\\")
            if i + 1 < len(lines) and lines[i + 1].startswith('msgstr "'):
                value = lines[i + 1][8:-1].replace('\\"', '"').replace("\\\\", "\\")
                out.append((key, value))
                i += 2
                continue
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--out", default=r"D:\Melvor2ZhPatch\tools\fixes_v2.tsv")
    ap.add_argument("--show", type=int, default=0)
    args = ap.parse_args()

    entries = read_po(args.po)
    fixed = collections.OrderedDict()

    for key, value in entries:
        if key in EXACT:
            if value != EXACT[key]:
                fixed[key] = (value, EXACT[key], "整条")
            continue

        # Several rules can hit the same entry (e.g. "max hit as min hit" needs
        # both the max and the min substitution), so apply them in one pass
        # instead of first-match-wins.
        new = value
        hits = []
        for scope, old, new_text, _why in RULES:
            if scope in key and old in new:
                new = new.replace(old, new_text)
                hits.append("%s: %s->%s" % (scope, old, new_text))

        if new != value:
            fixed[key] = (value, new, "; ".join(hits))

    stats = collections.Counter(why.split(":")[0] if ":" in why else why
                               for _, _, why in fixed.values())

    print("要改动的条目数:", len(fixed))
    for scope, n in stats.most_common():
        print("   %-24s %3d" % (scope, n))

    if args.show:
        print()
        for key, (old, new, why) in list(fixed.items())[:args.show]:
            print("  %-40s %s  =>  %s" % (key[:40], old[:26], new[:26]))

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 第二轮术语裁决，生成的精确修正清单\n")
        f.write("# 格式：msgid<TAB>新译文（逐条精确替换，不做模糊匹配）\n")
        for key, (old, new, why) in fixed.items():
            f.write("%s\t%s\n" % (key, new))
    print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
