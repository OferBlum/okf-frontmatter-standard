# OKF — a frontmatter standard for agent-maintained vaults

**Every file answers three closed questions, and says who wrote it and who checked it.**

When agents write into your notes, tags drift: `#ai`, `ai`, `AI`, `artificial-intelligence`.
Within a month the tags stop meaning anything. And once an agent has compiled a page, nothing
tells you whether a human ever read it. OKF fixes both with a small, enforced vocabulary and a
trust layer that keeps "generated" separate from "verified".

Part of [Digital Brain](https://github.com/OferBlum/personal-digital-brain-with-ai).

## The idea

**Three closed axes, one question each:**

| Axis | Question | Values |
|------|----------|--------|
| `type` | what kind of object is this | 8 values: `wiki-page`, `note`, `topic-hub`, `template`, `checklist`, `report`, `index`, `log` |
| `subject` | which area of life it belongs to | only what `SCHEMA.md` declares; **empty is a valid answer** |
| `tags` | what the file is for | only what `SCHEMA.md` declares, never with a leading `#` |

**The extension rule:** a new subject or tag goes into `SCHEMA.md` first, and only then gets
used. If you (or an agent) invent one inline, `validate.py` fails. That's on purpose: a
vocabulary that's allowed to drift is just free-form tags again.

**The trust layer** separates two things most systems conflate:

- `generated_by` / `generated_at`: *who produced this*: `human:me`, `process:ingest`, or `agent/version`.
- `verified: [{by, at}]`: *who read it and confirmed it*. **Absent means unverified**, which is
  the honest state for a page an agent compiled and nobody has checked. `okf_verify.py` is the only
  writer, so stamping is always a deliberate act.
- `status`: `draft` / `stable` / `deprecated`. Absent means `stable`.

These are two flat keys, never a nested `generated:` map. Obsidian Properties only renders flat
values, and a nested map hides both rows.

## How it works

```text
SCHEMA.md ──declares──► subjects · types · tags
    │
    ├── validate.py ──────────► every page in the content folders conforms (--hook: exit 2 on errors)
    ├── okf_verify.py ────────► stamps `verified`; --pending lists what nobody has checked
    ├── subject_candidates.py ► concepts linked from ≥3 pages that aren't subjects yet (you decide)
    └── list_tags.sh ─────────► tags actually in use, to compare against the schema
```

`okf.py` is the one frontmatter reader/writer. It never silently "fixes" a broken header. A
malformed header reads as empty and stays in the body verbatim, so a write-back changes nothing,
and adding fields above it is refused. Writes keep Obsidian's conventions: `[[links]]` quoted,
dates as plain strings, keys in a stable order.

## Files

```text
0 - System/
  SCHEMA.md                    # the controlled vocabulary (replace the example subjects/tags with yours)
  scripts/
    okf.py                     # reference reader/writer, page discovery, schema parsing
    validate.py                # conformance check, read-only
    okf_verify.py              # stamp / list / pending for the trust layer
    subject_candidates.py      # promotion suggestions, read-only
    list_tags.sh               # tags in use
    test_okf.py                # regression tests against a throwaway fixture vault
2 - Notes/Example note.md      # a conforming note
```

Scripts walk only the content folders (`7 - Wikipedia`, `2 - Notes`, `1 - Topics`), never the
vault root. The folder names are constants at the top of `okf.py`.

## Quickstart

1. Copy `0 - System/` into your vault, then replace the example subjects and tags in `SCHEMA.md` with your own.
2. `pip install pyyaml`, then `python3 "0 - System/scripts/validate.py"` to see what doesn't conform yet.
3. Review a page, then sign it: `python3 "0 - System/scripts/okf_verify.py" "2 - Notes/Example note.md"`.

Tests: `python3 -m unittest discover -s "0 - System/scripts" -p "test_*.py"`.

## License

MIT, see [LICENSE](LICENSE).
