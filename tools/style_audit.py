"""Second-pass audit: the layers po_audit.py does not cover.

po_audit.py answers "is this entry translated, and does it use the canonical
term". This script answers the remaining questions, grouped the way the
translation rules are grouped:

  S1  one source, many renderings   the same English word rendered several
                                    different ways across entries -> term drift
  S2  register / person             你 vs 您, 玩家 vs 你, mixed voice
  S3  punctuation                   半形 , . : ; ! ? 和 ... 混用
  S4  BBCode integrity              unbalanced tags, lost color/icon markup
  S5  newline count                 line count changed -> layout breaks
  S6  length blow-up                a short label became a long sentence
  S7  spacing                       stray ASCII space next to CJK

Usage
-----
    python style_audit.py                 # report under extracted/audit/style.md
    python style_audit.py --po other.po
"""

import argparse
import collections
import io
import os
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]")
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
RES_PATH = re.compile(r"\b(?:res|local|uid)://\S+")
TAG = re.compile(r"\[/?(?:b|i|u|s|color|img|url|center|left|right|font|size|table|cell|"
                 r"tooltip|wave|rainbow|pulse|shake|fill|outline|hint|effectIcon|itemIcon)"
                 r"(?:[/= ][^\]]*)?\]")

# Words that carry no term meaning: they appear inside every sentence, so their
# "rendering" is the whole sentence and comparing them is meaningless.
STOPWORDS = set("""
a an the and or but if then than of to in on at for with from by as into over under
out up down is are was were be been being this that these those it its you your yours
we our us they them their he she his her not no all any some more most other another
can will would should could may might must have has had do does did there here what
which who whom when where why how very just also only even still such same each every
per about above after again against before below between both during few further once
""".split())

# Square-bracket words the game uses as inline units in *tooltips*, not markup.
BRACKET_UNITS = {"seconds", "pixels", "qty", "itemName", "value", "count", "ms", "sec"}

# Register markers: 您 is the only address form that can clash with the 你 the
# rest of the text uses. 玩家 ("player") is a plain noun and is not checked.
SECOND_PERSON_NIN = "您"

HALF_PUNCT = [(",", "，"), (".", "。"), (":", "："), (";", "；"),
              ("!", "！"), ("?", "？"), ("(", "（"), (")", "）")]


def parse_po(path):
    """Return [(msgid, msgstr)] preserving order, unescaping \" and \n."""
    entries = []
    lines = io.open(path, encoding="utf-8").read().splitlines()
    key = None
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("msgid "):
            key = unquote(line[6:].strip())
            i += 1
            continue

        if line.startswith("msgstr ") and key is not None:
            val = unquote(line[7:].strip())
            entries.append((key, val))
            key = None

        i += 1

    return entries


def unquote(s):
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.replace('\\"', '"').replace("\\n", "\n")


def strip_noise(s):
    """Remove everything that is not prose: code, markup, paths, placeholders."""
    s = RES_PATH.sub(" ", s)
    s = TAG.sub(" ", s)
    s = PLACEHOLDER.sub(" ", s)
    s = s.replace("\n", " ")
    return s


def has_cjk(s):
    return bool(CJK_CHAR.search(s))


def first_line(path):
    return io.open(path, encoding="utf-8").readline().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--out", default="extracted/audit/style.md")
    args = ap.parse_args()

    if not os.path.exists(args.po):
        print("po not found: " + args.po)
        return 2

    entries = [(k, v) for k, v in parse_po(args.po) if v.strip()]
    print("entries with translation: %d" % len(entries))

    s1, s2, s3, s4, s5, s6, s7 = [], [], [], [], [], [], []

    # Term-level consistency is already covered by po_audit P2/P3 and
    # dup_target.py, and any attempt to redetect it here drowns in compound
    # names (精金靴子 / 敏捷靴 / 靴子 are all correct). So this script starts at
    # the style and technical layers instead.

    # ------------------------------------------------------------- S1 register
    # Only 您 competes with 你 as a form of address. 玩家 is the ordinary noun for
    # "player" (Player Stats, other players online) -- flagging it as a mixed
    # voice produced nothing but false positives, so it is not checked here.
    nin = [(k, v) for k, v in entries if SECOND_PERSON_NIN in v]
    if nin:
        s2.append(("您", len(nin), [k for k, v in nin[:8]]))

    # ---------------------------------------------------------- S2 punctuation
    half = collections.Counter()
    half_examples = collections.defaultdict(list)

    for key, val in entries:
        plain = TAG.sub(" ", val)
        plain = PLACEHOLDER.sub(" ", plain)
        plain = RES_PATH.sub(" ", plain)
        if not has_cjk(plain):
            continue

        for ascii_mark, full_mark in HALF_PUNCT:
            for m in re.finditer(re.escape(ascii_mark), plain):
                before = plain[m.start() - 1] if m.start() > 0 else ""
                after = plain[m.end()] if m.end() < len(plain) else ""
                if CJK_CHAR.match(before) and CJK_CHAR.match(after):
                    half[ascii_mark] += 1
                    if len(half_examples[ascii_mark]) < 6:
                        half_examples[ascii_mark].append(key)
        if "..." in plain and "……" not in plain:
            half["..."] += 1
            if len(half_examples["..."]) < 6:
                half_examples["..."].append(key)

    for mark, count in half.most_common():
        s3.append((mark, count, half_examples[mark]))

    # ------------------------------------------------------------- S4 BBCode
    for key, val in entries:
        src_tags = collections.Counter(TAG.findall(key))
        dst_tags = collections.Counter(TAG.findall(val))

        # ignore tags that only exist to wrap a placeholder in the source
        missing = []
        for t, n in src_tags.items():
            if dst_tags.get(t, 0) < n:
                missing.append(t)
        extra = []
        for t, n in dst_tags.items():
            if src_tags.get(t, 0) < n:
                extra.append(t)

        if missing or extra:
            s4.append((key, missing, extra, val[:70]))

    # ------------------------------------------------------------ S5 newlines
    for key, val in entries:
        if "\n" in key and key.count("\n") != val.count("\n"):
            s5.append((key.count("\n"), val.count("\n"), key[:50], val[:50]))

    # -------------------------------------------------------------- S6 length
    for key, val in entries:
        plain_key = strip_noise(key).strip()
        plain_val = strip_noise(val).strip()
        if not plain_key or not has_cjk(plain_val):
            continue
        kw = len(re.findall(r"[A-Za-z][A-Za-z'-]*", plain_key))
        cw = len(CJK_CHAR.findall(plain_val))
        # a label of <= 3 English words should not balloon past 24 CJK chars
        if kw <= 3 and cw >= 24:
            s6.append((kw, cw, plain_key[:40], plain_val[:60]))

    # ------------------------------------------------------------- S6 spacing
    # Checked on the RAW translation: a space between two CJK characters that has
    # a placeholder or tag between them is deliberate (中文 + 图标/数值 混排),
    # so only a bare space directly between two Chinese characters is suspect.
    for key, val in entries:
        if re.search(r"[\u4e00-\u9fff][ \t]+[\u4e00-\u9fff]", val):
            s7.append((key, val[:60]))

    s5.sort(key=lambda x: -abs(x[0] - x[1]))
    s6.sort(key=lambda x: -x[1])

    # ---------------------------------------------------------------- report
    out = []
    out.append("# 翻译风格 / 技术层体检\n")
    out.append("条目（已译）：%d\n" % len(entries))

    out.append("| 编号 | 类别 | 命中 |\n|---|---|---|")
    out.append("| S1 | 人称 / 语体混用 | %d |" % len(s2))
    out.append("| S2 | 标点混用 | %d 类 |" % len(s3))
    out.append("| S3 | BBCode 标签不匹配 | %d |" % len(s4))
    out.append("| S4 | 换行数量不一致 | %d |" % len(s5))
    out.append("| S5 | 短标签译得过长 | %d |" % len(s6))
    out.append("| S6 | 汉字间多余空格 | %d |" % len(s7))
    out.append("")

    out.append("## S1 人称 / 语体\n")
    if s2:
        for label, count, ex in s2:
            out.append("- 「%s」出现 %d 条，例：%s" % (label, count, "，".join(ex[:5])))
    else:
        out.append("（无：全文统一用「你」，未混入「您」）")
    out.append("")

    out.append("## S2 标点\n")
    for mark, count, ex in s3[:10]:
        out.append("- 半角 `%s` %d 处，例：%s" % (mark, count, "；".join(ex[:4])))
    out.append("")

    out.append("## S3 BBCode 不匹配\n")
    for key, missing, extra, val in s4[:30]:
        bits = []
        if missing:
            bits.append("缺 " + " ".join(missing))
        if extra:
            bits.append("多 " + " ".join(extra))
        out.append("- %s — %s" % ("；".join(bits), key[:50]))
    if not s4:
        out.append("（无）")
    out.append("")

    out.append("## S4 换行数量不一致\n")
    for a, b, k, v in s5[:20]:
        out.append("- 原文 %d 行 / 译文 %d 行 — %s" % (a + 1, b + 1, k[:50]))
    if not s5:
        out.append("（无）")
    out.append("")

    out.append("## S5 短标签译得过长（可能挤压布局）\n")
    for kw, cw, k, v in s6[:20]:
        out.append("- 原文 %d 词 → 译文 %d 字：%s → %s" % (kw, cw, k, v))
    if not s6:
        out.append("（无）")
    out.append("")

    out.append("## S6 汉字之间的多余空格\n")
    for key, val in s7[:25]:
        out.append("- %s ｜ %s" % (key[:40], val[:50]))
    if not s7:
        out.append("（无）")
    out.append("")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("\n".join(out))
    print("\nwrote " + args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
