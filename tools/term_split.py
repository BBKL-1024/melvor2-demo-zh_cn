"""Quantify how one English term is split across Chinese renderings.

`term_report.py` lists entries; this one answers the only question that matters
before a ruling: *how many entries use which Chinese word?*

The PO is keyed by English source text with no msgctxt, so "Wizard" appears
inside 100+ different keys and each batch translated it slightly differently.
To find the Chinese word that stands for the English term we do not try to align
word by word (impossible without a parser). Instead we score short CJK n-grams:

    coverage  = number of short labels containing the term that also contain the gram
    noise     = number of short labels NOT containing the term that contain the gram

Grams with high coverage and low noise are the candidates. Example for Wizard:

    === Wizard (124)
      巫师   96/124   noise 2
      法师   24/124   noise 0      <- minority variant, needs a ruling

Usage
-----
    python term_split.py --term Wizard --term Leather
    python term_split.py --auto 40
"""

import argparse
import collections
import io
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
NOISE = re.compile(r"\[[^\]]*\]|\{[^{}]*\}|<[^>]*>|%[sd]|\d+")


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


def words_of(key):
    clean = NOISE.sub(" ", key)
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", clean)


def grams(text, lo=1, hi=4):
    got = set()
    for run in CJK_RUN.findall(text):
        for n in range(lo, hi + 1):
            for i in range(len(run) - n + 1):
                got.add(run[i:i + n])
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--auto", type=int, default=0, help="take the N busiest terms")
    ap.add_argument("--max-words", type=int, default=4,
                    help="only consider keys with at most N words")
    ap.add_argument("--top", type=int, default=4, help="candidates to print per term")
    ap.add_argument("--min-coverage", type=int, default=2)
    args = ap.parse_args()

    entries = read_po(args.po)
    labels = [(k, v) for k, v in entries
              if v.strip() and CJK.search(v) and len(words_of(k)) <= args.max_words]

    # gram -> set of (key) for labels that do not mention a given term is expensive
    # per query, so pre-compute the gram -> label index once.
    index = collections.defaultdict(set)
    for key, value in labels:
        for g in grams(value):
            index[g].add(key)

    terms = list(args.term)
    if args.auto:
        freq = collections.Counter()
        for key, _ in labels:
            for w in {w for w in words_of(key) if len(w) >= 3 and w[0].isupper()}:
                freq[w] += 1
        terms = [w for w, _ in freq.most_common(args.auto)]

    total_labels = len(labels)
    for term in terms:
        pattern = re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"s?(?![A-Za-z])", re.IGNORECASE)
        pos = [(k, v) for k, v in labels if pattern.search(k)]
        if not pos:
            continue
        pos_keys = {k for k, _ in pos}
        scored = []
        for g, hits in index.items():
            cov = len(hits & pos_keys)
            if cov < args.min_coverage:
                continue
            noise = len(hits) - cov
            # A gram is only interesting when it concentrates inside this term's
            # entries: coverage high, leakage low.
            if noise > max(2, cov * 0.35):
                continue
            scored.append((cov, -noise, len(g), g))
        scored.sort(reverse=True)

        # Drop grams that are substrings of a stronger gram (巫师 inside 巫师帽).
        picked = []
        for cov, neg, ln, g in scored:
            if any(g in p for _, _, p in picked):
                continue
            picked.append((cov, -neg, g))
            if len(picked) >= args.top:
                break

        print("=== %s  (%d 条)  " % (term, len(pos))
              + "  |  ".join("%s %d/±%d" % (g, c, n) for c, n, g in picked))

    return 0


if __name__ == "__main__":
    sys.exit(main())
