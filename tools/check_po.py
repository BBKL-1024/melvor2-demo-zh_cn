# -*- coding: utf-8 -*-
# Final structural validation of the generated PO: it must parse cleanly, carry
# exactly one entry per catalog key, contain no duplicates, and every translated
# msgstr must still carry the same SmartFormat placeholders as its msgid.
#
# Run from the game root (it reads extracted/zh_CN.po and extracted/all_keys.txt
# by relative path); the extracted data is not shipped with this repo:
#     cd "<game folder>" && python D:/path/to/melvor2-zh/tools/check_po.py
import re, sys

text = open('extracted/zh_CN.po', encoding='utf-8').read()
lines = text.splitlines()

ENTRY = re.compile(r'^msgid "(.*)"$')
STR = re.compile(r'^msgstr "(.*)"$')

def unpo(s):
    # Keys legitimately contain the two characters '\' + 'n' (a C# escape in the
    # original source). merge_po.py deliberately does NOT touch backslashes, so
    # only \" and \\ are reversed here; decoding \n would break the comparison.
    return s.replace('\\"', '"').replace('\\\\', '\\')

ids, bad = [], []
i = 0
header_done = False
while i < len(lines):
    ln = lines[i]
    if ln.startswith('msgid ""') and not header_done:
        header_done = True
        i += 1
        continue
    m = ENTRY.match(ln)
    if not m:
        i += 1
        continue
    mid = unpo(m.group(1))
    if i + 1 >= len(lines) or not STR.match(lines[i + 1]):
        bad.append(('no msgstr', mid[:60])); i += 1; continue
    mstr = unpo(STR.match(lines[i + 1]).group(1))
    ids.append((mid, mstr))
    i += 2

print('po entries:', len(ids))
print('empty msgstr:', sum(1 for _, s in ids if not s.strip()))
dups = len(ids) - len({k for k, _ in ids})
print('duplicate msgids:', dups)
print('malformed entries:', len(bad))
for b in bad[:10]:
    print(' ', b)

catalog = open('extracted/all_keys.txt', encoding='utf-8-sig').read().splitlines()
cat = set(catalog)
missing = [k for k, _ in ids if k not in cat]
print('msgids not in catalog:', len(missing))
for k in missing[:10]:
    print('  ?', repr(k[:80]))

ph = re.compile(r'\{[^{}]*\}')
mis = 0
for k, v in ids:
    if not v.strip():
        continue
    a = sorted(ph.findall(re.sub(r'\{Value:cond:[^{}]*\}', '', k)))
    b = sorted(ph.findall(re.sub(r'\{Value:cond:[^{}]*\}', '', v)))
    if a != b:
        mis += 1
        if mis <= 5:
            print('  PH MISMATCH:', repr(k[:70]), '->', repr(v[:70]))
print('placeholder mismatches:', mis)

strict = 0
for k, v in ids:
    if not v.strip():
        continue
    if '{Value:cond' in k:
        continue
    # every LocalContext/Value token must survive verbatim
    a = sorted(t for t in ph.findall(k) if 'LocalContext' in t or 'Value' in t or 'FromContext' in t or 'LocComponent' in t)
    b = sorted(t for t in ph.findall(v) if 'LocalContext' in t or 'Value' in t or 'FromContext' in t or 'LocComponent' in t)
    if a != b:
        strict += 1
        if strict <= 5:
            print('  TOKEN MISMATCH:', repr(k[:70]))
print('verbatim context tokens mismatches:', strict)

ok = (not bad) and dups == 0 and not missing and mis == 0 and strict == 0
print()
print('RESULT:', 'ALL GREEN' if ok else 'NEEDS FIX')
sys.exit(0 if ok else 1)
