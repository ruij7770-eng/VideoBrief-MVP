import unittest


class TranscriptServiceTests(unittest.TestCase):
    def test_parses_vtt_and_long_timestamps(self):
        from videobrief.application.transcript import parse_timestamped_transcript, time_to_seconds

        rows = parse_timestamped_transcript("WEBVTT\n\n00:01:02.000 --> 00:01:05.000\n<font>測試字幕</font>\n")
        self.assertEqual(rows, [{"time": "01:02", "body": "測試字幕"}])
        self.assertEqual(time_to_seconds("01:02:03"), 3723)


class DecisionServiceTests(unittest.TestCase):
    def test_decision_builder_is_public_application_service(self):
        from videobrief.application.decision import build_decision_brief

        brief = {
            "content_type": "tutorial",
            "summary": "只保留必要字段",
            "content_model": {"items": [
                {"role": "result", "title": "结果", "detail": "只保留必要字段", "evidence_ids": ["E0003"]},
                {"role": "step", "title": "建立入口", "detail": "建立唯一入口", "evidence_ids": ["E0001"]},
                {"role": "pitfall", "title": "避免复杂", "detail": "字段太多会增加阻力", "evidence_ids": ["E0002"]},
            ]},
            "must_watch_segments": [],
            "metrics": {"duration_seconds": 120},
        }
        decision = build_decision_brief(brief)
        self.assertEqual(decision["answer"], "只保留必要字段")
        self.assertEqual(len(decision["takeaways"]), 2)


class QuestionAnsweringServiceTests(unittest.TestCase):
    def test_question_answering_is_safe_for_empty_points(self):
        from videobrief.application.question_answering import answer_from_brief

        answer = answer_from_brief({"chapters": [{
            "title": "字段设计", "body": "字段太多会增加录入阻力。", "points": [],
            "time": "01:20", "start_seconds": 80,
            "evidence": [{"evidence_id": "E0001", "time": "01:20", "seconds": 80, "quote": "字段太多会增加录入阻力。"}],
        }]}, "为什么字段不能太多？")
        self.assertTrue(answer["found"])
        self.assertEqual(answer["answer"], "字段太多会增加录入阻力。")


if __name__ == "__main__":
    unittest.main()
