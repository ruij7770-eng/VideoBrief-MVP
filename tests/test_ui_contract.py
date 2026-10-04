from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "videobrief" / "web"
JS = WEB / "assets" / "js"


class DecisionFirstUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (WEB / "index.html").read_text(encoding="utf-8")
        cls.css = (WEB / "assets" / "css" / "app.css").read_text(encoding="utf-8")
        cls.app = (JS / "app.js").read_text(encoding="utf-8")
        cls.decision = (JS / "components" / "decision.js").read_text(encoding="utf-8")
        cls.structure = (JS / "components" / "structure.js").read_text(encoding="utf-8")
        cls.chapters = (JS / "components" / "chapters.js").read_text(encoding="utf-8")
        cls.all_frontend = "\n".join((cls.html, cls.css, cls.app, cls.decision, cls.structure, cls.chapters))

    def test_result_starts_with_decision_brief_and_hides_the_input_panel(self):
        self.assertIn("data.decision_brief", self.decision)
        self.assertIn(".create.compact{display:none}", self.css)
        self.assertIn("真正重要的", self.decision)
        self.assertIn("观看建议", self.decision)
        self.assertIn(".decision-point .evidence{background:transparent", self.css)

    def test_redundant_insight_and_map_sections_are_not_rendered(self):
        self.assertNotIn("section('insights'", self.all_frontend)
        self.assertNotIn("section('map'", self.all_frontend)
        self.assertNotIn("['insights', '核心观点']", self.all_frontend)
        self.assertNotIn("['map', '内容地图']", self.all_frontend)

    def test_type_structure_and_chapters_use_progressive_disclosure(self):
        self.assertIn("el('details', 'type-item')", self.structure)
        self.assertIn("el('details', 'chapter')", self.chapters)
        self.assertIn("按需查证", self.chapters)
        self.assertIn('type="module" src="/assets/js/app.js"', self.html)


if __name__ == "__main__":
    unittest.main()
