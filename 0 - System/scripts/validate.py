#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — OKF conformance check. Read-only.

Enforces the three axes of SCHEMA.md (type / subject / tags) and the trust layer on every
page in the content folders. Prints errors and warnings.

Usage:
    python3 "0 - System/scripts/validate.py"           # report
    python3 "0 - System/scripts/validate.py" --hook    # also exit 2 if there are errors
"""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import okf

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUS_VALUES = {"draft", "stable", "deprecated"}
ACTOR_RE = re.compile(r"^(human:|process:|[\w.\-]+/)?[\w.\-]+$")


def as_list(v):
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def check(kind, meta, body, schema):
    """(errors, warnings) for one page."""
    subjects, types, tags_allowed = schema
    errors, warns = [], []

    if okf.has_broken_header(meta, body):
        return ["malformed frontmatter — fix it by hand"], []
    if not meta:
        return ["no frontmatter"], []

    # --- type: the one field OKF requires ---
    t = str(meta.get("type", "")).strip()
    if not t:
        errors.append("missing type")
    elif types is not None and t not in types:
        errors.append(f"type not in SCHEMA: {t}")

    # --- subject: closed list; empty is a valid answer ---
    subject = okf.nfc(re.sub(r"[\[\]\"]", "", str(meta.get("subject", ""))).strip())
    if subject and subjects is not None and subject not in subjects:
        errors.append(f"subject not in SCHEMA: {subject}")

    # --- tags ---
    tags = as_list(meta.get("tags"))
    for tg in tags:
        if tg.startswith("#"):
            errors.append(f"tag with a leading #: {tg}")
        elif tags_allowed is not None and okf.nfc(tg) not in tags_allowed:
            warns.append(f"tag not declared in SCHEMA: {tg}")

    # --- trust layer: flat keys, never a nested `generated:` map ---
    if "generated" in meta:
        errors.append("nested `generated` — split into generated_by and generated_at")
    by = str(meta.get("generated_by", "") or "").strip()
    at = str(meta.get("generated_at", "") or "").strip()
    if at and not by:
        errors.append("generated_at without generated_by")
    if by and not ACTOR_RE.match(by):
        warns.append(f"generated_by in an unfamiliar format: {by}")
    if at and not DATE_RE.match(at[:10]):
        warns.append(f"generated_at is not a date: {at}")
    if meta.get("verified") not in (None, "") and not isinstance(meta.get("verified"), list):
        errors.append("verified must be a list")
    st = str(meta.get("status", "")).strip()
    if st and st not in STATUS_VALUES:
        errors.append(f"invalid status: {st} (draft/stable/deprecated)")

    # --- compiled wiki pages also carry their provenance ---
    if kind == "wiki":
        if "wiki" not in tags:
            warns.append("tags without 'wiki'")
        lc = str(meta.get("last_compiled", ""))
        if not lc:
            errors.append("missing last_compiled")
        elif not DATE_RE.match(lc):
            errors.append(f"invalid date: {lc}")
        ws = meta.get("wiki_sources")
        if ws is None:
            warns.append("no wiki_sources")
        elif not isinstance(ws, list):
            errors.append("wiki_sources is not a list")

    return errors, warns


def main():
    schema = okf.read_schema()
    if schema == (None, None, None):
        print(f"No SCHEMA at {okf.rel(okf.SCHEMA)} — nothing to validate against.")
        sys.exit(2)
    n_err = n_warn = n_pages = 0
    for kind, p, meta, body in okf.iter_pages():
        n_pages += 1
        errors, warns = check(kind, meta, body, schema)
        n_err += len(errors)
        n_warn += len(warns)
        for m in errors:
            print(f"   🔴 {okf.rel(p)}: {m}")
        for m in warns:
            print(f"   🟡 {okf.rel(p)}: {m}")
    print(f"{n_pages} pages · 🔴 errors: {n_err} · 🟡 warnings: {n_warn}")
    if "--hook" in sys.argv and n_err:
        sys.exit(2)


if __name__ == "__main__":
    main()
