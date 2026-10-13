"""OKF regressions against a throwaway fixture vault."""
import contextlib
import importlib
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class OkfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='okf-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        env = patch.dict(os.environ, {'VAULT_ROOT': str(self.root), 'OKF_ACTOR': 'human:tester'})
        env.start()
        self.addCleanup(env.stop)
        for name in ('okf', 'validate', 'okf_verify', 'subject_candidates'):
            sys.modules.pop(name, None)
        self.O = importlib.import_module('okf')
        for folder in (self.O.SYS, self.O.WIKI, self.O.NOTES, self.O.TOPICS):
            folder.mkdir()
        shutil.copyfile(HERE.parent / 'SCHEMA.md', self.O.SCHEMA)
        self.schema = self.O.read_schema()

    def write(self, folder, name, text):
        path = folder / name
        path.write_text(text, encoding='utf-8')
        return path

    def errors(self, kind, text):
        V = importlib.import_module('validate')
        meta, body = self.O.split_header(text)
        return V.check(kind, meta, body, self.schema)

    # ---------- the reader/writer ----------

    def test_round_trip_keeps_dates_as_strings_and_links_quoted(self):
        text = ('---\ntype: note\nsubject: "[[Books]]"\ntags:\n  - idea\n'
                'generated_by: human:me\ngenerated_at: 2026-07-11\n---\nBody\n')
        meta, body = self.O.split_header(text)
        self.assertEqual(meta['generated_at'], '2026-07-11')
        self.assertEqual(self.O.render_page(meta, body), text)

    def test_bare_obsidian_values_are_read_not_lost(self):
        meta, _ = self.O.split_header('---\nsubject: [[Books]]\ntags:\n  - #idea\n---\n')
        self.assertEqual(meta['subject'], '[[Books]]')
        self.assertEqual(meta['tags'], ['#idea'])

    def test_malformed_header_stays_in_the_body_and_blocks_new_fields(self):
        text = '---\ntags: [broken\n---\nBody\n'
        meta, body = self.O.split_header(text)
        self.assertEqual((meta, body), ({}, text))
        self.assertTrue(self.O.has_broken_header(meta, body))
        self.assertEqual(self.O.render_page(meta, body), text)
        with self.assertRaises(ValueError):
            self.O.render_page({'type': 'note'}, body)

    def test_schema_is_read_from_its_sections(self):
        subjects, types, tags = self.schema
        self.assertIn('Books', subjects)
        self.assertEqual(len(types), 8)
        self.assertIn('wiki', tags)
        self.assertNotIn('wiki-page', tags)

    def test_discovery_skips_generated_catalog_report_and_symlinked_files(self):
        page = self.write(self.O.NOTES, 'idea.md', '---\ntype: note\n---\n')
        self.write(self.O.NOTES, '_cache.md', '---\ntype: note\n---\n')
        self.write(self.O.WIKI, 'index.md', '---\ntype: index\n---\n')
        self.write(self.O.WIKI, 'report.md', '---\ntype: report\n---\n')
        (self.O.NOTES / 'linked.md').symlink_to(page)
        self.assertEqual([p for _, p, _, _ in self.O.iter_pages()], [page])

    # ---------- validate ----------

    def test_closed_axes_reject_undeclared_values(self):
        errors, _ = self.errors('note', '---\ntype: essay\nsubject: "[[Cooking]]"\ntags:\n  - "#idea"\n---\n')
        self.assertIn('type not in SCHEMA: essay', errors)
        self.assertIn('subject not in SCHEMA: Cooking', errors)
        self.assertIn('tag with a leading #: #idea', errors)

    def test_empty_subject_is_a_valid_answer(self):
        self.assertEqual(self.errors('note', '---\ntype: note\nsubject:\ntags:\n  - idea\n---\n'), ([], []))

    def test_undeclared_tag_is_a_warning_not_an_error(self):
        errors, warns = self.errors('note', '---\ntype: note\ntags:\n  - recipes\n---\n')
        self.assertEqual(errors, [])
        self.assertIn('tag not declared in SCHEMA: recipes', warns)

    def test_trust_layer_must_be_flat(self):
        errors, _ = self.errors('note', '---\ntype: note\ngenerated:\n  by: human:me\n---\n')
        self.assertIn('nested `generated` — split into generated_by and generated_at', errors)
        errors, _ = self.errors('note', '---\ntype: note\ngenerated_at: 2026-07-11\n---\n')
        self.assertIn('generated_at without generated_by', errors)

    def test_wiki_pages_carry_provenance(self):
        errors, warns = self.errors('wiki', '---\ntype: wiki-page\ntags:\n  - wiki\n---\n')
        self.assertIn('missing last_compiled', errors)
        self.assertIn('no wiki_sources', warns)

    def test_hook_mode_fails_on_errors(self):
        self.write(self.O.NOTES, 'bad.md', '---\ntype: essay\n---\n')
        V = importlib.import_module('validate')
        with patch.object(sys, 'argv', ['validate.py', '--hook']), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_:
            V.main()
        self.assertEqual(exit_.exception.code, 2)

    # ---------- okf_verify and subject_candidates ----------

    def test_verify_stamps_once_and_backs_up_first(self):
        page = self.write(self.O.WIKI, 'Page.md', '---\ntype: wiki-page\n---\nBody\n')
        F = importlib.import_module('okf_verify')
        with contextlib.redirect_stdout(io.StringIO()):
            F.stamp([str(page)])
            F.stamp([str(page)])
        meta, body = self.O.read_page(page)
        self.assertEqual(len(meta['verified']), 1)
        self.assertEqual(meta['verified'][0]['by'], 'human:tester')
        self.assertEqual(body, 'Body\n')
        self.assertEqual(len(list((self.O.WIKI / '.backup').iterdir())), 1)

    def test_verify_refuses_files_outside_the_content_folders(self):
        outside = self.write(self.O.SYS, 'me.md', '---\ntype: note\n---\n')
        F = importlib.import_module('okf_verify')
        with contextlib.redirect_stdout(io.StringIO()):
            F.stamp([str(outside)])
        self.assertNotIn('verified', self.O.read_page(outside)[0])

    def test_subject_candidates_skip_existing_subjects(self):
        for i in range(3):
            self.write(self.O.NOTES, f'n{i}.md', '---\ntype: note\n---\n[[Sourdough]] and [[Books]]\n')
        C = importlib.import_module('subject_candidates')
        self.assertEqual(C.candidates(3), [(3, 'Sourdough')])


if __name__ == '__main__':
    unittest.main()
