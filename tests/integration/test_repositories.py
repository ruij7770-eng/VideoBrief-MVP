import copy
import tempfile
import unittest
from pathlib import Path


class SQLiteBriefRepositoryTests(unittest.TestCase):
    def test_save_get_and_list_use_explicit_legacy_table_columns(self):
        from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository

        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteBriefRepository(Path(folder) / "briefs.db")
            brief_id = repository.save({
                "schema_version": 4, "title": "标题", "summary": "摘要",
                "source": "pasted_transcript", "url": "", "chapters": [],
                "evidence_store": [], "key_insights": [], "content_model": {"template": "lecture", "items": []},
                "decision_brief": {"question": "问题", "answer": "答案", "watch_verdict": "直接阅读即可"},
            })
            loaded = repository.get(brief_id)
            self.assertEqual(loaded["title"], "标题")
            self.assertEqual(loaded["brief_id"], brief_id)
            self.assertEqual(repository.list_recent()[0]["id"], brief_id)

    def test_legacy_read_projection_does_not_rewrite_stored_json(self):
        from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository

        legacy = {
            "title": "旧记录", "summary": "摘要", "source": "pasted_transcript", "url": "",
            "chapters": [{"title": "章节", "time": "00:00", "body": "原文", "points": [],
                          "evidence": [{"time": "00:00", "seconds": 0, "quote": "原文"}]}],
        }
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteBriefRepository(Path(folder) / "briefs.db")
            brief_id = repository.save(copy.deepcopy(legacy))
            projected = repository.get(brief_id)
            stored = repository.get_raw(brief_id)
            self.assertEqual(stored, legacy)
            self.assertEqual(projected["compatibility"]["source_generation"], "canonical-v4")
            self.assertEqual(projected["compatibility"]["detected_generation"], "legacy-no-store")
            self.assertTrue(projected["evidence_store"])


class InMemoryJobRepositoryTests(unittest.TestCase):
    def test_reads_return_snapshots_and_terminal_jobs_are_bounded(self):
        from videobrief.infrastructure.jobs.memory import InMemoryJobRepository

        repository = InMemoryJobRepository(max_terminal=2, ttl_seconds=3600)
        first = repository.create("一")
        snapshot = repository.get(first["id"])
        snapshot["status"] = "tampered"
        self.assertEqual(repository.get(first["id"])["status"], "queued")
        for label in ("一", "二", "三"):
            job = first if label == "一" else repository.create(label)
            repository.update(job["id"], status="completed", progress=100)
        self.assertLessEqual(repository.count(), 2)


if __name__ == "__main__":
    unittest.main()
