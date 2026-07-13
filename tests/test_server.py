import tempfile
import unittest
import warnings
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
