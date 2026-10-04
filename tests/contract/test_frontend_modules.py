import tempfile
import unittest
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "videobrief" / "web"


class FrontendModuleContractTests(unittest.TestCase):
    def test_index_uses_external_css_and_es_modules(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('/assets/css/app.css', html)
        self.assertIn('type="module" src="/assets/js/app.js"', html)
        self.assertNotIn("<style>", html)
        self.assertNotIn("<script>", html)

    def test_api_state_and_components_are_separate_modules(self):
        app = (WEB / "assets/js/app.js").read_text(encoding="utf-8")
        self.assertIn("from './api.js'", app)
        self.assertIn("from './state.js'", app)
        self.assertIn("from './components/decision.js'", app)
        self.assertIn("from './components/structure.js'", app)
        self.assertIn("from './components/chapters.js'", app)
        components = "\n".join(path.read_text(encoding="utf-8") for path in (WEB / "assets/js/components").glob("*.js"))
        self.assertNotIn("fetch(", components)
        self.assertNotIn(".innerHTML", components)

    def test_css_structure_keeps_media_rules_top_level(self):
        css = (WEB / "assets/css/app.css").read_text(encoding="utf-8")
        self.assertEqual(css.count("{"), css.count("}"))
        self.assertIn(".metrics{display:flex;gap:28px;padding-top:19px;}", css)
        self.assertIn("@media(max-width:1100px)", css)
        self.assertIn("@media(max-width:760px)", css)

    def test_static_assets_are_served_by_app_factory(self):
        from fastapi.testclient import TestClient
        from videobrief.api.app import create_app
        from tests.contract.test_api_architecture import ModularApiContractTests

        with tempfile.TemporaryDirectory() as directory:
            _, container = ModularApiContractTests().make_client(directory)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                client = TestClient(create_app(container))
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/assets/css/app.css").status_code, 200)
            self.assertEqual(client.get("/assets/js/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
