import tempfile
import unittest
import warnings
from pathlib import Path


class FakePipeline:
    def run(self, command, progress=None):
        if progress:
            progress("finalizing", 95, "完成")
        return {
            "schema_version": 4,
            "title": "测试知识页",
            "summary": "摘要",
            "source": "pasted_transcript" if command.transcript else "local_whisper",
            "url": command.url,
            "content_type": "lecture",
            "evidence_store": [],
            "key_insights": [],
            "content_model": {"template": "lecture", "items": []},
            "chapters": [],
            "must_watch_segments": [],
            "metrics": {},
            "agent": {"mode": "fast"},
            "decision_brief": {"question": "问题", "answer": "答案", "watch_verdict": "直接阅读即可"},
        }


class ModularApiContractTests(unittest.TestCase):
    def make_client(self, directory):
        from videobrief.api.app import create_app
        from videobrief.api.dependencies import ApplicationContainer
        from videobrief.config import Settings
        from videobrief.infrastructure.jobs.memory import InMemoryJobRepository
        from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository

        settings = Settings(db_path=Path(directory) / "test.db", max_upload_bytes=8)
        container = ApplicationContainer(
            settings=settings,
            briefs=SQLiteBriefRepository(settings.db_path),
            jobs=InMemoryJobRepository(),
            pipeline=FakePipeline(),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi.testclient import TestClient
            return TestClient(create_app(container)), container

    def test_job_lifecycle_and_history_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.make_client(directory)
            created = client.post("/api/jobs", json={"transcript": "[00:00] 内容", "analysis_mode": "fast"})
            self.assertEqual(created.status_code, 200)
            job = created.json()
            self.assertTrue({"id", "status", "stage", "progress", "message", "result", "error"}.issubset(job))
            completed = client.get(f"/api/jobs/{job['id']}").json()
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["result"]["schema_version"], 4)
            history = client.get("/api/history").json()
            self.assertEqual(history[0]["id"], completed["result"]["brief_id"])

    def test_error_envelope_keeps_detail_and_machine_code(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.make_client(directory)
            response = client.post("/api/jobs", json={"url": "", "transcript": ""})
            self.assertEqual(response.status_code, 400)
            payload = response.json()
            self.assertIsInstance(payload["detail"], str)
            self.assertEqual(payload["error"]["code"], "INVALID_INPUT")

    def test_upload_limit_is_enforced_while_streaming(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.make_client(directory)
            response = client.post(
                "/api/jobs/upload?model_size=tiny&analysis_mode=fast",
                files={"media": ("sample.mp3", b"123456789", "audio/mpeg")},
            )
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["error"]["code"], "UPLOAD_TOO_LARGE")

    def test_unexpected_errors_use_safe_chinese_envelope(self):
        class BrokenPipeline:
            def run(self, *_args, **_kwargs):
                raise RuntimeError("secret internal path C:/private/file")

        with tempfile.TemporaryDirectory() as directory:
            _, container = self.make_client(directory)
            container.pipeline = BrokenPipeline()
            from fastapi.testclient import TestClient
            from videobrief.api.app import create_app
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                client = TestClient(create_app(container), raise_server_exceptions=False)
            response = client.post("/api/analyse", json={"transcript": "内容", "analysis_mode": "fast"})
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
            self.assertNotIn("private", response.text)

    def test_route_modules_do_not_own_sql_or_analysis(self):
        root = Path(__file__).resolve().parents[2] / "videobrief" / "api" / "routes"
        combined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
        for forbidden in ("sqlite3", "requests.", "make_brief(", "enhance_brief("):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
