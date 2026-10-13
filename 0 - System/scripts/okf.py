#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
okf.py — the reference frontmatter reader/writer for OKF. Every OKF script imports it.

Two promises:
  - A malformed header is never "fixed" silently. It reads as {} and stays in the body
    verbatim, so writing ({}, body) back reproduces the file unchanged.
  - A write keeps Obsidian happy: flat keys in a stable order, [[wikilinks]] quoted,
    dates left as plain strings, empty values written as `key:`.
"""
import os, re, shutil, unicodedata
import yaml
from pathlib import Path
from datetime import datetime

# Vault root: from VAULT_ROOT (for tests), or two levels above scripts/.
VAULT  = Path(os.environ.get("VAULT_ROOT") or Path(__file__).resolve().parents[2])
SYS    = VAULT / "0 - System"
TOPICS = VAULT / "1 - Topics"
NOTES  = VAULT / "2 - Notes"
WIKI   = VAULT / "7 - Wikipedia"
SCHEMA = SYS / "SCHEMA.md"

# The folders whose pages carry OKF frontmatter. Scripts walk only these, never the vault root.
CONTENT = (WIKI, NOTES, TOPICS)

# Catalog and guide files in the wiki folder are not pages.
NON_CONTENT = {"index.md", "log.md", "WIKI-GUIDE.md"}

PREFERRED_KEYS = ["type", "subject", "tags", "background", "status",
                  "wiki_sources", "last_compiled",
                  "generated_by", "generated_at", "verified"]


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def rel(path):
    return nfc(str(Path(path).relative_to(VAULT)))


def has_symlink(path):
    """A symlink anywhere on the path could point outside the vault; such paths are skipped."""
    p = Path(os.path.abspath(path))
    return any(item.is_symlink() for item in (p, *p.parents))


# ---------- reading ----------

# The one frontmatter fence: `---` lines (trailing blanks allowed); an empty header counts.
HEADER_FENCE = re.compile(r'\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|\Z)', re.S | re.M)


def _without_timestamps(cls):
    """Resolver map minus dates, so 2026-07-11 stays a string on read and is not quoted on write."""
    return {ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
            for ch, resolvers in cls.yaml_implicit_resolvers.items()}


class Loader(yaml.SafeLoader):
    pass


Loader.yaml_implicit_resolvers = _without_timestamps(yaml.SafeLoader)

# Obsidian writes bare values YAML misreads: [[link]] parses as a nested list and #tag as a
# comment. Quote them before parsing.
_UNSAFE = re.compile(r'^(\s*(?:[^:\n]+:|-)[ \t]+)((?:\[\[|#).*)$')


def _quote_unsafe(text):
    out = []
    for line in text.splitlines():
        m = _UNSAFE.match(line)
        if m:
            val = m.group(2).rstrip()
            line = m.group(1) + '"' + val.replace("\\", "\\\\").replace('"', '\\"') + '"'
        out.append(line)
    return "\n".join(out)


def _none_to_empty(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return [_none_to_empty(x) for x in v]
    if isinstance(v, dict):
        return {k: _none_to_empty(x) for k, x in v.items()}
    return v


def split_header(text):
    """(meta, body). A valid header is stripped from the body; a malformed one reads as {}."""
    m = HEADER_FENCE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.load(_quote_unsafe(m.group(1)), Loader=Loader)
    except (yaml.YAMLError, RecursionError, ValueError):
        return {}, text
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        return {}, text
    return {nfc(str(k)): _none_to_empty(v) for k, v in meta.items()}, text[m.end():]


def read_page(path):
    text = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    return split_header(text)


def has_broken_header(meta, body):
    """True for a page whose malformed header was kept, unparsed, at the top of the body."""
    return not meta and HEADER_FENCE.match(body) is not None


# ---------- writing ----------

class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)   # list items indented two spaces


def _repr_str(dumper, data):
    style = '"' if ("[[" in data or data.lstrip().startswith("#")) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


Dumper.add_representer(str, _repr_str)
Dumper.add_representer(type(None), lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""))
Dumper.yaml_implicit_resolvers = _without_timestamps(yaml.SafeDumper)


def _empty_to_none(v):
    if v == "":
        return None
    if isinstance(v, list):
        return [_empty_to_none(x) for x in v]
    if isinstance(v, dict):
        return {k: _empty_to_none(x) for k, x in v.items()}
    return v


def render_page(meta, body):
    if not meta:
        return body
    # New fields above a malformed header would create two headers — fix it by hand first.
    if HEADER_FENCE.match(body):
        raise ValueError("Malformed frontmatter must be fixed by hand before adding fields.")
    keys = [k for k in PREFERRED_KEYS if k in meta] + [k for k in meta if k not in PREFERRED_KEYS]
    fm = yaml.dump({k: _empty_to_none(meta[k]) for k in keys}, Dumper=Dumper,
                   allow_unicode=True, sort_keys=False, default_flow_style=False, width=10 ** 6)
    return "---\n" + fm.rstrip("\n") + "\n---\n" + body


def backup(paths, label):
    """Copy files to 7 - Wikipedia/.backup/<timestamp-label>/ before modifying them."""
    dest = WIKI / ".backup" / f"{datetime.now():%Y%m%d-%H%M%S}-{label}"
    for p in map(Path, paths):
        target = dest / p.relative_to(VAULT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    return dest


# ---------- discovery ----------

def iter_pages():
    """(kind, path, meta, body) for every top-level page in the content folders.

    Skips `_`-prefixed generated files, wiki catalogs, `type: report` pages, and symlinks.
    """
    for folder, kind in ((WIKI, "wiki"), (NOTES, "note"), (TOPICS, "topic")):
        if not folder.is_dir() or has_symlink(folder):
            continue
        for p in sorted(folder.glob("*.md")):
            name = nfc(p.name)
            if name.startswith("_") or has_symlink(p):
                continue
            if kind == "wiki" and name in NON_CONTENT:
                continue
            meta, body = read_page(p)
            if meta.get("type") == "report":
                continue
            yield kind, p, meta, body


# ---------- the schema ----------

def _section(text, header):
    """The text between a `## header` heading and the next ## heading."""
    m = re.search(rf"^##\s+{re.escape(header)}.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def read_schema(path=None):
    """(subjects, types, tags) declared in SCHEMA.md; each is None if the section is empty."""
    path = Path(path or SCHEMA)
    if not path.is_file():
        return None, None, None
    text = path.read_text(encoding="utf-8")
    subjects = {nfc(m.group(1).strip())
                for m in re.finditer(r"^-\s*\[\[([^\]]+)\]\]", _section(text, "subject"), re.M)}
    types = {m.group(1) for m in re.finditer(r"^-\s*`([^`]+)`", _section(text, "type"), re.M)}
    tags_sec = _section(text, "tags").split("### ")[0]
    tags = {nfc(m.group(1).strip()) for m in re.finditer(r"`([^`]+)`", tags_sec)}
    return (subjects or None), (types or None), (tags or None)
