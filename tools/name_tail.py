"""按物品类别检查译名的构词是否与英文尾词相符。

每个英文尾词在中文里有一个惯用字（Ore→矿、Bar→锭、Boots→靴 ……），译名里不带这个字
的，要么是分类错了，要么是译名漏了中心词。只报「尾词命中、但译文没有对应汉字」的情形，
不猜该改什么。

    python name_tail.py                 # 读 extracted/zh_CN.po + extracted/context.json
    python name_tail.py --out extracted/audit/name_tail.md
"""

import argparse
import io
import json
import os
import re
import sys

# 尾词 -> 译文里必须出现的候选字（任一命中即通过）
TAIL_RULES = {
    "Boots": "靴",
    "Potion": "药",
    "Gloves": "手",
    "Amulet": "护身符|符|项链",
    "Ring": "戒",
    "Helmet": "盔",
    "Shield": "盾",
    "Crossbow": "弩",
    "Legs": "腿",
    "Cape": "披风|斗篷",
    "Hat": "帽",
    "Sword": "剑",
    "Staff": "杖",
    "Wand": "杖",
    "Body": "甲|衣|袍",
    "Torso": "躯|甲",
    "Head": "头|首",
    "Arrows": "箭",
    "Bar": "锭",
    "Bottoms": "腿|裤|下装",
    "Robes": "袍|衣",
    "Log": "原木|木",
    "Tree": "树",
    "Bow": "弓",
    "Platebody": "铠|胸甲",
    "Platelegs": "腿甲|护腿",
    "Chaps": "腿|裤|护腿",
    "Cowl": "头巾|兜帽|帽",
    "Dagger": "匕首",
    "Bolts": "矢|箭|螺栓",
    "Javelin": "标枪",
    "Ore": "矿",
    "Bait": "饵",
    "Arrowtips": "箭头",
    "Vambraces": "护臂|臂",
    "Defender": "护剑|盾",
    "Lantern": "灯",
    "Scimitar": "弯刀|刀",
    "Mallet": "锤",
    "Trap": "陷阱",
    "Leather": "皮",
    "Rune": "符文",
    "Vein": "矿脉|脉",
    "Pack": "包|袋",
    "Upgrades": "升级",
    "Bonus": "加成",
}

SKIP_TAIL = {"I", "II", "III", "IV", "V", "2", "3", "4"}


def unpo(text):
    return text.replace('\\"', '"').replace("\\\\", "\\")


def parse_po(path):
    entries, msgid = {}, None
    for line in io.open(path, encoding="utf-8").read().splitlines():
        s = line.rstrip()
        if s.startswith('msgid "'):
            if s == 'msgid ""':
                msgid = None
                continue
            msgid = unpo(s[7:-1])
        elif s.startswith('msgstr "') and msgid is not None:
            entries[msgid] = unpo(s[8:-1])
            msgid = None
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--ctx", default="extracted/context.json")
    ap.add_argument("--out", default="extracted/audit/name_tail.md")
    args = ap.parse_args()

    po = parse_po(args.po)
    ctx = json.load(io.open(args.ctx, encoding="utf-8"))

    # msgid -> 它出现过的 Category 集合（只关心有分类的物品/对象名）
    names = {}
    for key, items in ctx.items():
        cats = {e["Category"] for e in items if "Category" in e}
        if cats and any(e.get("field") in ("Singular", "DisplayName") for e in items):
            names[key] = cats

    bad = []
    checked = 0

    for msgid, cats in names.items():
        if not re.match(r"^[\x20-\x7e]+$", msgid):
            continue
        words = msgid.split()
        if len(words) < 2:
            continue

        tail = words[-1]
        if tail in SKIP_TAIL or tail not in TAIL_RULES:
            continue

        zh = po.get(msgid, "")
        if not zh:
            continue

        checked += 1
        if not re.search(TAIL_RULES[tail], zh):
            bad.append((tail, msgid, zh, sorted(cats)))

    bad.sort(key=lambda r: (r[0], r[1]))

    out = io.StringIO()
    out.write("# 物品名构词核对\n\n")
    out.write("按英文尾词查中文译名是否带了对应的中心字（Ore→矿、Bar→锭、Boots→靴 …）。\n")
    out.write("命中的条目 %d 条，其中译文缺中心字 %d 条。\n\n" % (checked, len(bad)))
    out.write("| 尾词 | 原文 | 译文 | 分类 |\n|---|---|---|---|\n")
    for tail, msgid, zh, cats in bad:
        out.write("| %s | %s | %s | %s |\n"
                  % (tail, msgid.replace("|", "\\|"), zh.replace("|", "\\|"),
                     ", ".join(cats).replace("MelvorBase:", "")))

    io.open(args.out, "w", encoding="utf-8", newline="\n").write(out.getvalue())
    print("checked %d, missing-center-word %d -> %s" % (checked, len(bad), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
