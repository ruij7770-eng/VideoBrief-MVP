import tempfile
import time
import unittest
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from videobrief.api.app import create_app, _cleanup_stale_uploads
from videobrief.api.dependencies import ApplicationContainer
from videobrief.bootstrap import build_pipeline
from videobrief.config import Settings
from videobrief.infrastructure.jobs.memory import InMemoryJobRepository
from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository
import videobrief_server
from videobrief_server import analyse_payload


class ApiContractTests(unittest.TestCase):
    def test_returns_structured_brief_from_pasted_transcript(self):
        result = analyse_payload({"transcript": "[00:00] 开始。\n[01:00] 总结：完成。", "url": "", "analysis_mode": "fast"})
        self.assertEqual(result["source"], "pasted_transcript")
        self.assertEqual(result["chapters"][0]["time"], "00:00")
        self.assertEqual(result["summary"], "完成")
        self.assertEqual(result["agent"]["mode"], "fast")

    def test_agent_status_endpoint_never_exposes_key(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi.testclient import TestClient
            response = TestClient(videobrief_server.app).get("/api/agent/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("configured", payload)
        self.assertNotIn("api_key", payload)

    def test_video_question_endpoint_returns_timestamped_evidence(self):
        original_db = videobrief_server.DB_PATH
        with tempfile.TemporaryDirectory() as directory:
            videobrief_server.DB_PATH = Path(directory) / "test.db"
            try:
                brief = analyse_payload({
                    "transcript": "[00:00] 介绍数据库。\n[01:20] 字段太多会增加录入阻力。",
                    "url": "",
                })
                brief_id = videobrief_server._save_result(brief)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from fastapi.testclient import TestClient
                    response = TestClient(videobrief_server.app).post(
                        f"/api/briefs/{brief_id}/ask", json={"question": "为什么字段不要太多？"}
                    )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["found"])
                self.assertEqual(payload["evidence"][0]["time"], "01:20")
            finally:
                videobrief_server.DB_PATH = original_db


class JobCapacityTests(unittest.TestCase):
    def _container(self, upload_dir, jobs):
        settings = Settings(upload_dir=upload_dir, db_path=upload_dir / "briefs.db")
        return ApplicationContainer(
            settings=settings,
            briefs=SQLiteBriefRepository(settings.db_path),
            jobs=jobs,
            pipeline=build_pipeline(settings),
        )

    def test_rejects_new_jobs_when_capacity_is_reached(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = InMemoryJobRepository()
            for _ in range(2):
                jobs.create("busy")
            container = self._container(Path(directory), jobs)
            with TestClient(create_app(container)) as client:
                response = client.post("/api/jobs", json={"transcript": "[00:00] test", "analysis_mode": "fast"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()["error"]["code"], "JOB_CAPACITY_REACHED")

    def test_stale_uploads_are_removed_on_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_dir = Path(directory) / "uploads"
            upload_dir.mkdir()
            stale = upload_dir / "stale.mp4"
            old = upload_dir / "recent.mp4"
            stale.write_bytes(b"a")
            old.write_bytes(b"b")
            past = time.time() - 25 * 3600
            import os
            os.utime(stale, (past, past))
            removed = _cleanup_stale_uploads(upload_dir)
            self.assertEqual(removed, 1)
            self.assertFalse(stale.exists())
            self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
