"""Remove the ASCII space that survives behind a full-width colon.

The v9 fix batch swapped half-width ':' for '：' but kept the space that used to
separate the label from its value, leaving '幸福度： {0:P0}'. Chinese typography
does not put a space after a full-width colon, so strip it -- but only when the
colon is full-width, and only a single space, and never when what follows is
another placeholder-free ASCII word that would then glue to the label.
"""

import io
import os
import re
import sys

PO = sys.argv[1] if len(sys.argv) > 1 else "extracted/zh_CN.po"
DRY = "--dry-run" in sys.argv

PAT = re.compile(r"：([ \t]+)(?=[^\s])")


def unpo(s):
    return s.replace('\\"', '"').replace("\\\\", "\\")


def po_escape(s):
    return s.replace('"', '\\"')


lines = io.open(PO, encoding="utf-8").read().splitlines(True)
changed = []
i = 0
while i < len(lines):
    ln = lines[i]
    if ln.startswith("msgstr "):
        raw = ln[len("msgstr "):].rstrip("\n")
        assert raw.startswith('"') and raw.endswith('"'), raw
        body = unpo(raw[1:-1])
        new = PAT.sub("：", body)
        if new != body:
            lines[i] = 'msgstr "' + po_escape(new) + '"\n'
            changed.append((body, new))
    i += 1

for old, new in changed[:12]:
    print("  %-58s => %s" % (old[:58], new[:58]))
print("cleaned entries: %d" % len(changed))

if DRY:
    print("dry run -- file not written")
    sys.exit(0)

io.open(PO, "w", encoding="utf-8", newline="\n").write("".join(lines))
print("wrote %s" % PO)
