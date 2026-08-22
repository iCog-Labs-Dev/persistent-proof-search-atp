"""
test_projector.py — Tests for the MORK projector (journal -> <proof_id>.metta)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from projector import project_event_journal, project_journal_to_file
from projector.writer import DEFAULT_OUTPUT_DIR

JOURNAL_PATH = (
    Path(__file__).resolve().parent.parent / "event_journals" / "event_journal.json"
)


class TestProjectorCore(unittest.TestCase):
    """Most significant projection behaviors."""

    def test_move_and_attempt_infer_state_id_from_edges(self):
        journal = {
            "proof_id": "test-proof",
            "events": [
                {
                    "revision": 1,
                    "payload": {
                        "ops": [
                            {
                                "op": "upsert_node",
                                "label": "Move",
                                "id": "test-proof/m1",
                                "fields": {"summary": "s", "status": "open", "kind": "reduction"},
                            },
                            {
                                "op": "add_edge",
                                "rel": "PROPOSES",
                                "src": "test-proof/s1",
                                "dst": "test-proof/m1",
                                "edge_id": "test-proof/e1",
                            },
                            {
                                "op": "upsert_node",
                                "label": "Attempt",
                                "id": "test-proof/a1",
                                "fields": {"move_summary": "a", "status": "supported", "worker": "w"},
                            },
                            {
                                "op": "add_edge",
                                "rel": "ON_STATE",
                                "src": "test-proof/a1",
                                "dst": "test-proof/s1",
                                "edge_id": "test-proof/e2",
                            },
                        ]
                    },
                }
            ],
        }
        commands = project_event_journal(journal)
        move_cmd = next(c for c in commands if "(Move " in c)
        attempt_cmd = next(c for c in commands if "(Attempt " in c)
        self.assertIn('(Move "test-proof" "m1" "s1"', move_cmd)
        self.assertIn('(Attempt "test-proof" "a1" "s1"', attempt_cmd)

    def test_events_processed_in_revision_order(self):
        journal = {
            "proof_id": "test",
            "events": [
                {
                    "revision": 3,
                    "payload": {"ops": [{"op": "upsert_node", "label": "Claim", "id": "test/c2", "fields": {"statement": "Second", "status": "conjectural"}}]},
                },
                {
                    "revision": 1,
                    "payload": {"ops": [{"op": "upsert_node", "label": "State", "id": "test/s1", "fields": {"description": "First", "status": "open", "kind": "or"}}]},
                },
                {
                    "revision": 2,
                    "payload": {"ops": [{"op": "upsert_node", "label": "Claim", "id": "test/c1", "fields": {"statement": "Middle", "status": "conjectural"}}]},
                },
            ],
        }
        commands = project_event_journal(journal)
        self.assertLess(commands.index(next(c for c in commands if "(State " in c)),
                        commands.index(next(c for c in commands if '"Middle"' in c)))
        self.assertLess(commands.index(next(c for c in commands if '"Middle"' in c)),
                        commands.index(next(c for c in commands if '"Second"' in c)))


class TestProjectJournalToFile(unittest.TestCase):
    """End-to-end: real journal -> .metta file named after the proof."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_dir = Path(self.tmp.name)

    def test_even_sum_journal_writes_named_metta_file(self):
        out_path = project_journal_to_file(JOURNAL_PATH, self.out_dir)

        self.assertEqual(out_path.name, "even-sum-proof.metta")
        content = out_path.read_text(encoding="utf-8")

        add_atoms = [l for l in content.splitlines() if l.startswith("!(add-atom")]
        self.assertEqual(len(add_atoms), 8)  # 4 nodes + 4 edges from the journal

        self.assertIn("!(mm2-exec &mork 1)", content)
        self.assertIn('(State "even-sum-proof" "s1"', content)
        self.assertIn('(Edge "e2" PROPOSES "s1" "m1")', content)

    def test_default_output_dir_is_mork_proofs(self):
        self.assertEqual(DEFAULT_OUTPUT_DIR.name, "proofs")
        with patch("projector.writer.DEFAULT_OUTPUT_DIR", self.out_dir):
            out_path = project_journal_to_file(JOURNAL_PATH)
        self.assertEqual(out_path.parent, self.out_dir)


if __name__ == "__main__":
    unittest.main()
