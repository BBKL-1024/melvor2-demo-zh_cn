"""Round-3 rulings: the long tail of small terms.

Same contract as gen_fixes_v2: every rule is (scope substring, old, new) and is
expanded into one exact `msgid -> new msgstr` line, so apply_fixes.py only ever
rewrites the msgstr of a listed msgid.

Run from the game folder:
    python gen_fixes_v3.py
"""

import argparse
import collections
import io
import sys

# (scope, old, new, why)
RULES = [
    ("Fortified String", "弓弦", "绳子", "String 是亚麻做的绳子，不是 Bowstring"),
    ("Reinforced String", "弓弦", "绳子", "同上"),
    ("Drain", "汲取", "吸取", "同族 生命/血液/精神吸取 都用吸取"),
    ("Maximum Ward", "守护", "结界", "Ward 全库多为「结界」(被结界抵消/最大结界值)"),
    ("Ward", "破护药水", "破界药水", "Ward 统一为结界"),
    ("Ward", "护盾", "结界", "Ward 统一为结界"),
    ("Stats", "数值", "属性", "Stats 面板统一为「属性」"),
    ("stats", "数值", "属性", "同上（小写）"),
    ("Thieving", "盗窃", "偷窃", "技能名是「偷窃」"),
    ("Farming Automation", "耕作", "农耕", "技能名是「农耕」"),
    ("Lanterns", "灯笼", "提灯", "Lantern 全库为「提灯」"),
    ("Enclosures", "围场", "围栏", "Enclosures 单词条目为「围栏」"),
    ("Potato", "马铃薯", "土豆", "Potato 单词条目为「土豆」"),
    ("Glowfin", "辉鳍", "荧光鳍", "Glowfin 单词条目为「荧光鳍」"),
    ("Sharp Fletching", "尖锐", "锐利", "Sharp 单词条目为「锐利」"),
    ("Barrier", "障壁", "屏障", "Barrier 单词条目为「屏障」"),
    ("[Observation]", "观察", "观测", "Observation 统一为「观测」"),
    ("Collectables", "收藏品", "收集品", "Collectables 单词条目为「收集品」"),
    ("Plaguewing", "瘟翼", "瘟疫翼", "Plaguewing 单词条目为「瘟疫翼」"),
    ("<Artist Name>", "艺术家", "画师", "credits 里 artist 用「画师」"),
    ("Cost to Block", "封锁", "格挡", "Block 是战斗格挡"),
    ("Runecrafter", "符文师", "符文制作师", "技能名是「符文制作」"),
    ("Ameria", "阿梅利亚", "阿梅里亚", "地名，3 条里 2 条是阿梅里亚"),
    ("Ceedyr", "塞迪尔", "西迪尔", "地名统一"),
    ("Iridan", "伊利丹", "伊里丹", "地名统一"),
    ("Deedree", "迪德瑞", "迪德里", "地名统一"),
    ("Hobgolbin", "霍布哥布林", "大哥布林", "hobgoblin 的常规译名"),
    # 19 条用「腿甲」，只有 3 条用「护腿」：多数派是腿甲
    ("Legs", "护腿", "腿甲", "多数派是「腿甲」，护腿只有 3 条"),
    ("Crush", "水压术", "水碾", "同族法术：风碾/土碾/火碾"),
    ("Toolbelt", "工具带", "工具栏", "4 条里都是「工具栏」"),
    ("Stormhorn Wildebeast", "野兽", "荒野兽", "Wildebeast 统一为「荒野兽」"),
]

EXACT = {}


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
    ap.add_argument("--out", default=r"D:\Melvor2ZhPatch\tools\fixes_v3.tsv")
    args = ap.parse_args()

    entries = read_po(args.po)
    fixed = collections.OrderedDict()

    for key, value in entries:
        if key in EXACT:
            if value != EXACT[key]:
                fixed[key] = (value, EXACT[key], "整条")
            continue

        new = value
        hits = []
        for scope, old, new_text, _why in RULES:
            if scope in key and old in new:
                new = new.replace(old, new_text)
                hits.append(scope)

        if new != value:
            fixed[key] = (value, new, ",".join(hits))

    print("要改动的条目数:", len(fixed))
    for scope, n in collections.Counter(w for _, _, w in fixed.values()).most_common():
        print("   %-28s %3d" % (scope, n))

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 第三轮裁决：长尾小词，精确逐条\n")
        for key, (old, new, _why) in fixed.items():
            f.write("%s\t%s\n" % (key, new))
    print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
