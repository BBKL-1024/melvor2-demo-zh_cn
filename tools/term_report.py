"""Show how one English term is currently rendered, across every entry using it.

This is the tool for the question "is this word translated consistently?". The PO
is keyed by English source text, so a term like `Logs`, `String` or `Wizard` shows
up inside many different entries, and each one was translated in a different batch.
Those batches disagreed more often than not.

Reading the output tells you, in one glance, whether a term needs a ruling:

    $ python term_report.py --term Wizard
    === Wizard  (24 entries)
      Adept Wizard Boots       -> 精通巫师靴
      Adept Wizard Robe        -> 熟练法师长袍      <- outlier: 法师
      Air Wizard               -> 风巫师

Then you record the ruling in glossary.tsv and fix the outliers.

Usage
-----
    python term_report.py --term Wizard --term Logs
    python term_report.py --auto 60          # busiest terms in short labels
    python term_report.py --auto 60 --out extracted/audit/terms.md
"""

import argparse
import collections
import io
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]")
STOP = {
    "the", "a", "an", "of", "in", "to", "and", "or", "for", "with", "on", "at",
    "by", "from", "is", "are", "was", "be", "this", "that", "it", "you", "your",
    "not", "all", "any", "can", "will", "has", "have", "no", "yes", "max", "min",
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


def words_of(key):
    clean = re.sub(r"\{[^{}]*\}", " ", key)
    clean = re.sub(r"\[[^\]]*\]", " ", clean)
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", clean)


def term_entries(entries, term, limit, max_words=0):
    pattern = re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"s?(?![A-Za-z])")
    hits = []
    for key, value in entries:
        if not value.strip() or not CJK.search(value):
            continue
        if max_words and len(words_of(key)) > max_words:
            continue
        if pattern.search(key):
            hits.append((key, value))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="extracted/zh_CN.po")
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--auto", type=int, default=0)
    ap.add_argument("--max-words", type=int, default=0,
                    help="only look at keys with at most N words (item names, labels)")
    ap.add_argument("--limit", type=int, default=14)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    entries = read_po(args.po)
    terms = list(args.term)

    if args.auto:
        freq = collections.Counter()
        for key, value in entries:
            if not value.strip() or not CJK.search(value):
                continue
            ws = words_of(key)
            if args.max_words and len(ws) > args.max_words:
                continue
            for w in {w for w in ws if len(w) >= 3 and w.lower() not in STOP}:
                if w[0].isupper():
                    freq[w] += 1
        terms = [w for w, _ in freq.most_common(args.auto)]

    if not terms:
        print("nothing to do -- pass --term or --auto")
        return 1

    lines = []
    for term in terms:
        hits = term_entries(entries, term, args.limit, args.max_words)
        if not hits:
            continue
        lines.append("")
        lines.append("=== %s  (%d entries)" % (term, len(hits)))
        for key, value in hits[:args.limit]:
            lines.append("  %-44s -> %s" % (key[:44], value[:40]))
        if len(hits) > args.limit:
            lines.append("  ... %d more" % (len(hits) - args.limit))

    text = "\n".join(lines)
    print(text)
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
        print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
