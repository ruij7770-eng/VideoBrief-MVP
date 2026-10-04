import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "videobrief"


class DependencyDirectionContractTests(unittest.TestCase):
    def test_domain_has_no_framework_or_infrastructure_dependencies(self):
        content = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "domain").glob("*.py"))
        for forbidden in ("fastapi", "sqlite3", "requests", "videobrief.infrastructure", "videobrief.api"):
            self.assertNotIn(forbidden, content)

    def test_application_does_not_construct_infrastructure_adapters(self):
        content = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "application").glob("*.py"))
        self.assertNotIn("videobrief.infrastructure", content)
        self.assertNotIn("fastapi", content)
        self.assertNotIn("sqlite3", content)

    def test_legacy_root_modules_are_thin_compatibility_facades(self):
        project = ROOT.parent
        limits = {
            "videobrief_service.py": 100,
            "videobrief_agent.py": 80,
            "videobrief_bilibili.py": 40,
            "videobrief_server.py": 140,
        }
        for filename, maximum in limits.items():
            lines = (project / filename).read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), maximum, f"{filename} 不应重新积累业务逻辑")


if __name__ == "__main__":
    unittest.main()
