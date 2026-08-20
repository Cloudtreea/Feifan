import json
import re
import unittest
from pathlib import Path


HTML = Path(__file__).parents[1].joinpath("memory_station.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path(__file__).parents[1].joinpath("question_bank_manifest.json").read_text(encoding="utf-8"))
PAIR_PATTERN = re.compile(r'pair\("([^"]+)","([^"]+)","([^"]+)"')
FULL_PAIR_PATTERN = re.compile(
    r'pair\("([^"]+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)"'
)


class QuestionBankTest(unittest.TestCase):
    def test_manifest_matches_playable_knowledge_universe(self):
        aliases = {"china-ancient": "ancient", "china-modern": "modern", "world": "world"}
        knowledge = {key: set() for key in aliases.values()}
        for module_id, knowledge_id, _relation_type in PAIR_PATTERN.findall(HTML):
            knowledge[aliases[module_id]].add(knowledge_id)
        actual = {key: len(values) for key, values in knowledge.items()}
        self.assertEqual(MANIFEST["knowledgeTotals"], actual)

    def test_each_playable_relation_has_twenty_four_pairs(self):
        counts = {}
        for module_id, _knowledge_id, relation_type in PAIR_PATTERN.findall(HTML):
            counts[(module_id, relation_type)] = counts.get((module_id, relation_type), 0) + 1
        required = {
            ("china-ancient", "time-event"),
            ("china-ancient", "system-impact"),
            ("china-modern", "time-event"),
            ("china-modern", "event-impact"),
            ("world", "time-event"),
            ("world", "event-impact"),
        }
        for group in required:
            self.assertGreaterEqual(counts.get(group, 0), 24, group)

    def test_display_text_is_unique_inside_each_relation(self):
        grouped = {}
        for module_id, _knowledge_id, relation_type, _a_label, a_text, _b_label, b_text in FULL_PAIR_PATTERN.findall(HTML):
            texts = grouped.setdefault((module_id, relation_type), set())
            self.assertNotIn(a_text, texts, (module_id, relation_type, a_text))
            self.assertNotIn(b_text, texts, (module_id, relation_type, b_text))
            texts.update((a_text, b_text))

    def test_cold_dynasty_foundation_dates_are_removed(self):
        for text in ("公元前1046年", "公元前770年", "公元前202年", "东汉建立",
                     "581年", "618年", "960年", "1271年", "1368年", "1644年"):
            self.assertNotIn(text, HTML)


if __name__ == "__main__":
    unittest.main()
