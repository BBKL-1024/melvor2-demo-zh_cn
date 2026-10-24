"""Flag adjacent characters that read identically inside one Chinese run.

「瘟疫翼」 is the motivating case: 瘟(wēn) 疫(yì) 翼(yì) -- two neighbouring syllables
share the same reading, which makes the name hard to say and hard to remember.

Only *neighbouring* characters are compared, and only inside one uninterrupted run of
Chinese characters, so `物品 xN` never produces a false hit across the gap. Identical
character pairs (渐渐, 常常) are skipped: that repetition is normal Chinese, not a defect.

    python homophone.py                     # uses extracted/zh_CN.po
    python homophone.py --po path/to.po --out extracted/audit/homophone.md
"""

import argparse
import io
import re
import sys

from pypinyin import Style, pinyin

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

# Bbcode tags carry no sound; drop them before reading the text.
BBCODE_RE = re.compile(r"\[/?(?:b|i|u|s|color[^\]]*|img[^\]]*|center|left|right|url[^\]]*)\]",
                       re.IGNORECASE)


def unpo(text):
    return text.replace('\\"', '"').replace("\\\\", "\\")


def parse_po(path):
    entries = []
    msgid = None
    for line in io.open(path, encoding="utf-8").read().splitlines():
        s = line.rstrip()
        if s.startswith('msgid "'):
            if s == 'msgid ""':
                msgid = None
                continue
            msgid = unpo(s[7:-1])
        elif s.startswith('msgstr "') and msgid is not None:
            entries.append((msgid, unpo(s[8:-1])))
            msgid = None
    return entries


def chinese_runs(text):
    """Split into uninterrupted runs of Chinese characters."""
    runs, cur = [], []
    for ch in text:
        if CJK_RE.match(ch):
            cur.append(ch)
        elif cur:
            runs.append("".join(cur))
            cur = []
    if cur:
        runs.append("".join(cur))
    return runs


def find_hits(text):
    """Return [(char_a, char_b, reading, position)] for identical adjacent readings."""
    hits = []
    plain = BBCODE_RE.sub("", text)

    for run in chinese_runs(plain):
        if len(run) < 2:
            continue

        readings = pinyin(run, style=Style.TONE, heteronym=False, errors=lambda x: None)
        if len(readings) != len(run):
            continue

        for i in range(len(run) - 1):
            a, b = run[i], run[i + 1]
            if a == b:
                continue                # deliberate repetition, not a clash
            pa, pb = readings[i][0], readings[i + 1][0]
            if pa and pa == pb:
                hits.append((a, b, pa, i))

    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--out", default="extracted/audit/homophone.md")
    ap.add_argument("--max-chars", type=int, default=24,
                    help="report entries whose Chinese length is at most this many chars")
    args = ap.parse_args()

    entries = parse_po(args.po)
    rows = []

    for msgid, msgstr in entries:
        if not msgstr:
            continue
        hits = find_hits(msgstr)
        if not hits:
            continue
        length = len(CJK_RE.findall(BBCODE_RE.sub("", msgstr)))
        rows.append((length, msgid, msgstr, hits))

    short = [r for r in rows if r[0] <= args.max_chars]
    long_ = [r for r in rows if r[0] > args.max_chars]

    short.sort(key=lambda r: (r[0], r[1]))
    long_.sort(key=lambda r: (r[0], r[1]))

    out = io.StringIO()
    out.write("# 相邻同音检查\n\n")
    out.write("同一段连续汉字里，相邻两字读音完全相同（含声调）。叠字已排除。\n\n")
    out.write("- 短条目（汉字 <= %d）：%d 条 —— 名称类，基本都是要改的\n"
              % (args.max_chars, len(short)))
    out.write("- 长条目（汉字 >  %d）：%d 条 —— 普通句子里同音很常见，按需挑\n\n"
              % (args.max_chars, len(long_)))

    out.write("## 短条目\n\n| 原文 | 译文 | 撞音 |\n|---|---|---|\n")
    for length, msgid, msgstr, hits in short:
        clash = " / ".join("%s%s=%s" % (a, b, p) for a, b, p, _ in hits)
        out.write("| %s | %s | %s |\n"
                  % (msgid.replace("|", "\\|"), msgstr.replace("|", "\\|").replace("\n", " "), clash))

    out.write("\n## 长条目\n\n| 原文 | 译文 | 撞音 |\n|---|---|---|\n")
    for length, msgid, msgstr, hits in long_:
        clash = " / ".join("%s%s=%s" % (a, b, p) for a, b, p, _ in hits)
        preview = msgstr.replace("|", "\\|").replace("\n", " ")
        if len(preview) > 70:
            preview = preview[:70] + "…"
        out.write("| %s | %s | %s |\n"
                  % (msgid[:60].replace("|", "\\|"), preview, clash))

    io.open(args.out, "w", encoding="utf-8", newline="\n").write(out.getvalue())
    print("short: %d   long: %d   -> %s" % (len(short), len(long_), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
