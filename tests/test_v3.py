import time
import unittest

from videobrief_service import answer_from_brief, make_brief, time_to_seconds
from videobrief_server import _jobs, _jobs_lock, _run_with_live_progress


class StructuredBriefV3Tests(unittest.TestCase):
    def test_long_timestamp_is_converted_to_seconds(self):
        self.assertEqual(time_to_seconds("01:20:15"), 4815)

    def test_chapter_contains_verifiable_evidence_range(self):
        rows = [
            {"time": "00:00", "body": "今天介绍个人知识库。"},
            {"time": "01:00", "body": "建立统一入口可以减少信息遗漏。"},
            {"time": "02:00", "body": "总结：先收集，再整理，最后每周回顾。"},
        ]
        result = make_brief(rows)
        chapter = result["chapters"][0]
        self.assertIn("start_seconds", chapter)
        self.assertIn("end_seconds", chapter)
        self.assertTrue(chapter["evidence"])
        self.assertIn("quote", chapter["evidence"][0])
        self.assertEqual(result["language"], "zh-CN")

    def test_metrics_are_available_for_fast_understanding(self):
        result = make_brief([
            {"time": "00:00", "body": "第一部分讲核心方法。"},
            {"time": "10:00", "body": "总结：执行核心方法。"},
        ])
        self.assertEqual(result["metrics"]["duration_seconds"], 600)
        self.assertGreaterEqual(result["metrics"]["estimated_read_minutes"], 1)

    def test_commentary_separates_fact_opinion_and_uncertainty_locally(self):
        result = make_brief([
            {"time": "00:00", "body": "今天评论这项新政策及其影响。"},
            {"time": "00:30", "body": "事实是政策将在下个月开始实施。"},
            {"time": "01:00", "body": "我认为它能降低小企业的成本。"},
            {"time": "01:30", "body": "但长期效果仍不确定，尚未有完整数据。"},
        ])
        self.assertEqual(result["content_type"], "commentary")
        self.assertEqual(result["content_model"]["template"], "commentary")
        roles = {item["role"] for item in result["content_model"]["items"]}
        self.assertIn("opinion", roles)
        self.assertIn("uncertainty", roles)

    def test_tutorial_produces_a_quick_understanding_fingerprint(self):
        result = make_brief([
            {"time": "00:00", "body": "今天演示如何安装工具。"},
            {"time": "01:00", "body": "第一步打开设置界面，点击安装按钮。"},
            {"time": "02:00", "body": "然后配置参数并运行命令。"},
            {"time": "03:00", "body": "总结：完成配置后检查参数和运行结果。"},
        ])
        self.assertEqual(result["content_type"], "tutorial")
        self.assertEqual(result["fingerprint"]["type_label"], "操作教程")
        self.assertEqual(result["content_model"]["template"], "tutorial")
        roles = [item["role"] for item in result["content_model"]["items"]]
        self.assertIn("goal", roles)
        self.assertEqual(roles[-1], "result")
        self.assertTrue(all(item["evidence_ids"] for item in result["content_model"]["items"]))
        self.assertGreaterEqual(len(result["key_insights"]), 1)
        self.assertIn("information_density", result["fingerprint"])
        self.assertIn("recommended_path", result["fingerprint"])
        self.assertNotIn("mastery", result)

    def test_visual_instructions_create_a_content_map_and_watch_segment(self):
        result = make_brief([
            {"time": "00:00", "body": "今天解决安装失败的问题。"},
            {"time": "01:00", "body": "原因是配置参数错误。"},
            {"time": "02:00", "body": "现在看屏幕演示，点击设置按钮并选择安装目录。"},
            {"time": "03:00", "body": "最后重新运行命令即可完成。"},
        ])
        self.assertTrue(result["content_map"])
        self.assertEqual(result["content_map"][0]["kind"], "问题")
        self.assertTrue(result["must_watch_segments"])
        segment = result["must_watch_segments"][0]
        self.assertEqual(segment["start_seconds"], 120)
        self.assertIn("画面", segment["reason"])

    def test_each_transcript_row_becomes_addressable_evidence(self):
        rows = [
            {"time": "00:00", "body": "第一条原始字幕。"},
            {"time": "00:17", "body": "第二条原始字幕。"},
            {"time": "00:42", "body": "第三条原始字幕。"},
        ]
        result = make_brief(rows)
        self.assertEqual(
            [item["evidence_id"] for item in result["evidence_store"]],
            ["E0001", "E0002", "E0003"],
        )
        self.assertEqual(result["evidence_store"][1]["time"], "00:17")
        self.assertEqual(result["evidence_store"][1]["quote"], "第二条原始字幕。")
        evidence_ids = {
            item["evidence_id"]
            for chapter in result["chapters"]
            for item in chapter["evidence"]
        }
        self.assertEqual(evidence_ids, {"E0001", "E0002", "E0003"})

    def test_local_insights_link_to_exact_evidence(self):
        result = make_brief([
            {"time": "00:00", "body": "第一条观点说明问题。"},
            {"time": "00:25", "body": "第二条观点给出方法。"},
        ])
        insight = result["key_insights"][0]
        self.assertTrue(insight["evidence_ids"])
        self.assertEqual(insight["evidence_ids"][0], insight["evidence"][0]["evidence_id"])
        self.assertEqual(insight["seconds"], insight["evidence"][0]["seconds"])

    def test_semantic_chunking_preserves_all_source_evidence_ids(self):
        rows = [
            {"time": f"00:{index * 5:02d}", "body": f"连续字幕片段{index}"}
            for index in range(9)
        ]
        result = make_brief(rows)
        chapter_ids = {
            item["evidence_id"]
            for chapter in result["chapters"]
            for item in chapter["evidence"]
        }
        self.assertEqual(chapter_ids, {f"E{index:04d}" for index in range(1, 10)})
        self.assertNotIn(None, chapter_ids)

    def test_generic_intro_word_does_not_create_false_watch_segment(self):
        result = make_brief([
            {"time": "00:00", "body": "今天演示如何提升工作效率。"},
            {"time": "01:00", "body": "核心方法是减少重复步骤。"},
        ])
        self.assertEqual(result["must_watch_segments"], [])

    def test_question_answer_jumps_to_the_best_matching_evidence(self):
        brief = {
            "chapters": [{
                "title": "数据库设置",
                "body": "先建立数据库。字段太多会增加录入阻力。",
                "points": ["只保留必要字段。"],
                "time": "00:00",
                "start_seconds": 0,
                "evidence": [
                    {"evidence_id": "E0001", "time": "00:00", "seconds": 0, "quote": "先建立数据库。"},
                    {"evidence_id": "E0002", "time": "02:10", "seconds": 130, "quote": "字段太多会增加录入阻力。"},
                ],
            }]
        }
        answer = answer_from_brief(brief, "为什么字段不能太多？")
        self.assertTrue(answer["found"])
        self.assertEqual(answer["time"], "02:10")
        self.assertEqual(answer["seconds"], 130)
        self.assertEqual(answer["evidence"][0]["evidence_id"], "E0002")

    def test_question_answer_uses_video_evidence_and_admits_missing_information(self):
        brief = make_brief([
            {"time": "00:00", "body": "今天讲数据库设计。"},
            {"time": "01:20", "body": "字段太多会增加录入阻力，所以只保留必要字段。"},
            {"time": "03:00", "body": "最后每周检查一次。"},
        ])
        answer = answer_from_brief(brief, "为什么字段不要太多？")
        self.assertTrue(answer["found"])
        self.assertTrue(answer["evidence"])
        self.assertEqual(answer["evidence"][0]["time"], "01:20")

        missing = answer_from_brief(brief, "作者推荐什么手机？")
        self.assertFalse(missing["found"])
        self.assertIn("未明确提及", missing["answer"])

    def test_blocking_work_emits_progress_heartbeat(self):
        job_id = "progress-regression"
        with _jobs_lock:
            _jobs[job_id] = {"progress": 15}

        def slow_work():
            time.sleep(2.3)
            return "done"

        value = _run_with_live_progress(
            job_id, slow_work, start=15, ceiling=76, message="正在处理"
        )
        self.assertEqual(value, "done")
        self.assertGreater(_jobs[job_id]["progress"], 15)
        with _jobs_lock:
            _jobs.pop(job_id, None)


if __name__ == "__main__":
    unittest.main()
