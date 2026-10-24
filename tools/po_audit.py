"""Audit the Melvor2 Chinese PO and point at the entries most likely to be wrong.

Built for a PO that is keyed by English source text with no msgctxt, where the
translations were produced in bulk batches. In that situation there are exactly
four kinds of findable mistakes, and this script looks for all of them:

  P0  untranslated          msgstr is empty                     -> English on screen
  P1  leftover English      msgstr still has real English words -> half-translated
  P2  term drift            a word's canonical rendering is missing from a phrase
                            that contains that word               -> "String" = 弓弦
  P3  overloaded target     one Chinese string serves many different English
                            sources                               -> flattened meaning
  P4  near-duplicate keys   keys differing only in case / plural / whitespace
                            that were translated differently      -> inconsistent

Everything is stripped of BBCode, placeholders and resource paths first, so
`[img height=1.25em]res://...` no longer looks like untranslated text.

Usage
-----
    python po_audit.py                     # report + tsv files under extracted/audit
    python po_audit.py --po path/to.po
    python po_audit.py --min-term-len 3    # ignore words shorter than this
"""

import argparse
import collections
import io
import os
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]")

# Only real BBCode tags are stripped: the game also uses square brackets as plain
# text (e.g. "[Sighting]"), and eating those would create fake problems. Tags are
# either lower-case led (img, effectIcon, ...) or one of the well-known upper-case
# ones, and they may carry attributes ([img height=1.25em]).
BBCODE = re.compile(
    r"\[/?(?:[a-z][A-Za-z0-9_]*|b|i|u|s|color|img|url|center|left|right|"
    r"font|size|table|cell|tooltip|wave|rainbow|pulse|shake|fill|outline|hint)"
    r"(?:[/= ][^\]]*)?\]"
)
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
RES_PATH = re.compile(r"\b(?:res|local|uid)://\S+")
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6,8}\b")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
# <qty>, <total>, <RecipeType> are chat-command slots the game fills in itself.
ANGLE = re.compile(r"<[^<>\n]{1,40}>")
# Roman numerals are part of the name (Crafting Station III), not a leftover word.
ROMAN = re.compile(r"^(?:I{1,3}|IV|V|VI{0,3}|IX|X|XI|XII)$")
# Words that are legitimately kept in English: brands, protocols, key names and
# the asset tokens the game substitutes at runtime ([Icon], {ItemIcon} ...).
ALLOW_EN = {
    "Patreon", "Steam", "Melvor", "Idle", "Mod", "Mods", "Cloud", "GUID", "SDK",
    "NPC", "NPCs", "base64", "ALPHA", "Alpha", "Alt", "Ctrl", "Shift", "Left",
    "Right", "Click", "Hold", "Icon", "Icons", "ItemIcon", "EventIcon",
    "EntityIcon", "AmmoTypeIcon", "DungeonIcon", "ConstellationIcon",
    "PlayerName", "Name", "Chat", "Discord", "Reddit", "Wiki", "BETA", "DLC",
    "SSE", "API", "Auto", "CDN", "URL", "GPU", "FPS",
    # runtime placeholders kept verbatim in the translation on purpose
    "Companion", "Player", "base", "Fest", "Next",
}


def strip_noise(text):
    text = BBCODE.sub(" ", text)
    text = PLACEHOLDER.sub(" ", text)
    text = RES_PATH.sub(" ", text)
    text = HEX_COLOR.sub(" ", text)
    return text


def read_po(path):
    """Parse msgid/msgstr pairs, keeping the two-character \\n escape intact."""
    lines = io.open(path, encoding="utf-8").read().splitlines()
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('msgid "') and line != 'msgid ""':
            key = unpo(line[7:-1])
            if i + 1 < len(lines) and lines[i + 1].startswith('msgstr "'):
                value = unpo(lines[i + 1][8:-1])
                entries.append((key, value))
                i += 2
                continue
        i += 1
    return entries


def unpo(s):
    return s.replace('\\"', '"').replace("\\\\", "\\")


def is_cjk(s):
    return CJK.search(s) is not None


def write_tsv(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("english\tchinese\thint\n")
        for row in rows:
            fh.write("\t".join(c.replace("\t", " ") for c in row) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--out-dir", default="extracted/audit")
    ap.add_argument("--min-term-len", type=int, default=3)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    if not os.path.exists(args.po):
        print("ERROR: %s not found" % args.po)
        return 2

    os.makedirs(args.out_dir, exist_ok=True)
    entries = read_po(args.po)
    print("entries:", len(entries))

    # ---------------------------------------------------------------- P0 missing
    p0 = [(k, "", "msgstr 为空") for k, v in entries if not v.strip()]

    # --------------------------------------------------------------- P1 leftover
    p1 = []
    for key, value in entries:
        if not value.strip():
            continue
        body = strip_noise(value)
        if not is_cjk(body):
            continue
        # Roman numerals, brands and runtime asset tokens all survive translation
        # on purpose; flagging them buried the real leftovers under 144 rows.
        words = [w for w in WORD.findall(ANGLE.sub(" ", body))
                 if w not in ALLOW_EN and not ROMAN.match(w)]
        if words:
            p1.append((key, value, "残留英文: " + " ".join(words[:6])))

    # same as source but with real words (already counted as untranslated)
    p1_same = [
        (k, v, "译文与原文完全相同")
        for k, v in entries
        if v.strip() and v == k
        and [w for w in WORD.findall(strip_noise(k))
             if w not in ALLOW_EN and not ROMAN.match(w)]
    ]

    # ------------------------------------------------------------ P2 term drift
    # A single-word key gives that word's canonical rendering; phrases containing
    # the word are expected to reuse it. Missing means either a synonym was used
    # (fine, needs eyes) or the wrong sense was picked (the bug we are hunting).
    canonical = {}
    display = {}
    # Function words and unit-ish labels never behave like a reusable term: "Max"
    # inside "Max Hit" is not the same word as the "Max" attribute heading.
    skip_terms = {
        "the", "and", "for", "with", "from", "this", "that", "you", "your", "all",
        "any", "not", "max", "min", "value", "height", "width", "name", "entity",
        "component", "category", "will", "can", "has", "have", "out", "per", "new",
    }
    for key, value in entries:
        if not value.strip() or not is_cjk(value):
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", key) and len(key) >= args.min_term_len:
            if key.lower() in skip_terms:
                continue
            body = strip_noise(value).strip()
            if body and len(body) <= 8:
                canonical.setdefault(key.lower(), body)
                display.setdefault(key.lower(), key)

    # A hand-written glossary wins over the auto-derived one: once a term has been
    # ruled on, every phrase containing it must use that rendering.
    glossary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary.tsv")
    if os.path.exists(glossary_path):
        for raw in io.open(glossary_path, encoding="utf-8-sig").read().splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            cells = raw.split("\t")
            if len(cells) >= 2 and cells[1].strip():
                # Keys are case-folded: the PO carries both 'Stone' and 'stone',
                # and treating them as two terms doubled every finding.
                canonical[cells[0].strip().lower()] = cells[1].strip()
                display[cells[0].strip().lower()] = cells[0].strip()
        print("glossary terms loaded:", len(canonical))
    for plural in [k for k in canonical if k.endswith("s") and k[:-1] in canonical]:
        canonical.pop(plural, None)
        display.pop(plural, None)

    drift = collections.defaultdict(list)
    key_words = {}
    for key, value in entries:
        if not value.strip() or not is_cjk(value) or " " not in key:
            continue
        body_nows = re.sub(r"\s+", "", strip_noise(value))
        raw_words = re.findall(r"[A-Za-z][A-Za-z'\-]*", strip_noise(key))
        # Long sentences paraphrase by nature; only short labels (item names, UI
        # captions) are expected to reuse a term verbatim. This keeps the report a
        # worklist instead of a wall of text.
        if len(raw_words) > 4:
            continue
        words = {w.lower() for w in raw_words}
        words |= {w[:-1] for w in words if len(w) > 3 and w.endswith("s")}
        key_words[(key, value)] = (body_nows, words)

    def resolve(word):
        """Map a word to its ruling, tolerating plural/singular spelling.

        The PO carries both the singular and the plural of the same noun (Cow and
        Cows, Stat and Stats); without this the same term is reported twice and
        half of those rows never get a ruling.
        """
        for candidate in (word, word[:-1]) if word.endswith("s") else (word,):
            ruled = canonical.get(candidate)
            if ruled:
                return candidate, ruled
        return None, None

    for (key, value), (body_nows, words) in key_words.items():
        seen = set()
        for word in sorted(words):
            term, chinese = resolve(word)
            if not term or term in seen:
                continue
            seen.add(term)
            # A ruling may list accepted renderings separated by '|'. Chinese drops
            # suffixes when compounding (靴子 -> 靴, 骨头 -> 骨, 箭头 -> 箭), so
            # demanding one exact string would flag hundreds of correct names.
            accepted = [c.strip() for c in chinese.split("|") if c.strip()]
            if any(a in body_nows for a in accepted):
                continue
            parts = [p for p in re.split(r"[与和的及或/、，]", "".join(accepted)) if p]
            if any(p in body_nows for p in parts):
                continue
            drift[term].append((key, value, "期望含「%s」" % " / ".join(accepted)))

    drift_rows = []
    for term, items in sorted(drift.items(), key=lambda kv: -len(kv[1])):
        for key, value, hint in items:
            drift_rows.append((key, value, display.get(term, term) + ": " + hint))

    # ------------------------------------------------------- P3 overloaded target
    target = collections.defaultdict(set)
    for key, value in entries:
        if value.strip() and is_cjk(value):
            target[value].add(key)
    p3 = []
    for chinese, sources in target.items():
        if len(sources) < 3:
            continue
        # Plural/singular of the same word is not a problem.
        roots = {re.sub(r"(?:s|es)$", "", s.lower()) for s in sources}
        if len(roots) < 3:
            continue
        p3.append((" / ".join(sorted(sources)[:4]), chinese,
                   "%d 个不同英文 → 同一译文" % len(sources)))
    p3.sort(key=lambda r: -int(r[2].split(" ")[0]))
    p3 = p3[:120]

    # ---------------------------------------------------------- P4 near-duplicate
    grouped = collections.defaultdict(set)
    for key, value in entries:
        if not value.strip():
            continue
        norm = re.sub(r"[^a-z0-9 ]", "", key.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        grouped[norm.rstrip("s")].add((key, value))
    p4 = []
    for norm, items in grouped.items():
        if len(items) < 2:
            continue
        values = {v for _, v in items}
        if len(values) > 1:
            for key, value in sorted(items):
                p4.append((key, value, "同组译法不一: " + " | ".join(sorted(values)[:3])))

    # ------------------------------------------------------------------- report
    total = len(entries)
    translated = sum(1 for _, v in entries if v.strip())
    lines = []
    lines.append("# 翻译体检报告")
    lines.append("")
    lines.append("- 条目总数：%d，已译 %d（%.1f%%）" % (total, translated, 100.0 * translated / total))
    lines.append("")
    lines.append("| 优先级 | 类别 | 条目数 | 说明 |")
    lines.append("|---|---|---|---|")
    lines.append("| P0 | 未翻译 | %d | 界面直接显示英文 |" % len(p0))
    lines.append("| P1 | 残留英文 | %d | 中文里还夹着英文词 |" % (len(p1) + len(p1_same)))
    lines.append("| P2 | 术语漂移 | %d | 短语没沿用该词的既定译法 |" % len(drift_rows))
    lines.append("| P3 | 一译多源 | %d | 同一中文对应多个英文 |" % len(p3))
    lines.append("| P4 | 近似重复 | %d | 大小写/单复数条目译法不一 |" % len(p4))
    lines.append("")

    if drift:
        lines.append("## 漂移最严重的词（先看这些）")
        lines.append("")
        for term, items in sorted(drift.items(), key=lambda kv: -len(kv[1]))[:args.top]:
            lines.append("- **%s** → 既定译法「%s」，%d 条短语没用到：%s"
                         % (display.get(term, term), canonical[term], len(items),
                            "，".join(k for k, _, _ in items[:4])))
        lines.append("")

    if p3:
        lines.append("## 一译多源 Top 15")
        lines.append("")
        for english, chinese, hint in p3[:15]:
            lines.append("- 「%s」 ← %s" % (chinese, english))
        lines.append("")

    write_tsv(os.path.join(args.out_dir, "p0_untranslated.tsv"), p0)
    write_tsv(os.path.join(args.out_dir, "p1_leftover_english.tsv"), p1 + p1_same)
    write_tsv(os.path.join(args.out_dir, "p2_term_drift.tsv"), drift_rows)
    write_tsv(os.path.join(args.out_dir, "p3_overloaded.tsv"), p3)
    write_tsv(os.path.join(args.out_dir, "p4_near_duplicate.tsv"), p4)

    report = os.path.join(args.out_dir, "report.md")
    with io.open(report, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    print("\n".join(lines))
    print()
    print("wrote", report, "and 5 tsv files in", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
