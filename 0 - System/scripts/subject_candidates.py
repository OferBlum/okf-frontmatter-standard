#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
subject_candidates.py — concepts worth promoting to a subject. Read-only.

A candidate is a [[link]] target mentioned from at least N different pages that is not
already a subject in SCHEMA.md. The script suggests; you decide, by editing SCHEMA.md.

Usage: python3 "0 - System/scripts/subject_candidates.py" [N]   (default N=3)
"""
import sys, re
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import okf

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def candidates(n):
    subjects = okf.read_schema()[0] or set()
    refs = defaultdict(set)            # target -> pages that mention it
    for _, p, meta, body in okf.iter_pages():
        for m in LINK_RE.finditer(body + " " + str(meta.get("subject", ""))):
            target = okf.nfc(m.group(1).split("|")[0].split("/")[-1].strip())
            refs[target].add(okf.nfc(p.stem))
    found = [(len(pages), target) for target, pages in refs.items()
             if len(pages) >= n and target not in subjects]
    return sorted(found, reverse=True)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    found = candidates(n)
    print(f"💡 Subject candidates (mentioned from >= {n} pages): {len(found)}")
    for count, target in found:
        print(f"   {count}×  {target}")


if __name__ == "__main__":
    main()
