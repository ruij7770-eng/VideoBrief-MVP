import copy
import unittest


LEGACY = {
    "title": "旧知识页",
    "summary": "旧摘要",
    "source": "pasted_transcript",
    "url": "",
    "chapters": [
        {
            "title": "字段设计",
            "time": "01:20",
            "start_seconds": 80,
            "body": "字段太多会增加录入阻力。",
            "points": [],
            "evidence": [
                {"time": "01:20", "seconds": 80, "quote": "字段太多会增加录入阻力。"}
            ],
        }
    ],
}


class HistoryCompatibilityTests(unittest.TestCase):
    def test_empty_legacy_points_do_not_crash_question_answering(self):
        from videobrief_service import answer_from_brief

        answer = answer_from_brief(copy.deepcopy(LEGACY), "为什么字段不能太多？")
        self.assertTrue(answer["found"])
        self.assertEqual(answer["answer"], "字段太多会增加录入阻力。")

    def test_legacy_projection_is_deterministic_without_overwriting_raw_data(self):
        from videobrief.application.compatibility import normalize_brief_for_read

        original = copy.deepcopy(LEGACY)
        first = normalize_brief_for_read(LEGACY)
        second = normalize_brief_for_read(LEGACY)
        projected_again = normalize_brief_for_read(first)
        self.assertEqual(LEGACY, original)
        self.assertEqual(first["evidence_store"], second["evidence_store"])
        self.assertEqual(projected_again, first)
        self.assertEqual(first["schema_version"], 4)
        self.assertEqual(first["evidence_store"][0]["source"], "legacy_chapter_projection")
        self.assertEqual(first["chapters"][0]["evidence"][0]["evidence_id"], first["evidence_store"][0]["evidence_id"])

    def test_untrusted_compatibility_metadata_cannot_override_shape_detection(self):
        from videobrief.application.compatibility import normalize_brief_for_read

        cases = [
            "not-a-mapping",
            {"source_generation": "unknown", "projected": True, "stored_payload_unchanged": True},
            {"source_generation": 7, "projected": True, "stored_payload_unchanged": True},
            {"source_generation": "decision-v3", "projected": False, "stored_payload_unchanged": True},
            {"source_generation": "typed-v2", "projected": True, "stored_payload_unchanged": True},
        ]
        for metadata in cases:
            with self.subTest(metadata=metadata):
                raw = copy.deepcopy(LEGACY)
                raw["compatibility"] = metadata
                projected = normalize_brief_for_read(raw)
                self.assertEqual(projected["compatibility"]["source_generation"], "canonical-v4")
                self.assertTrue(projected["compatibility"]["projected"])

    def test_malformed_truthy_generation_fields_are_safely_reprojected(self):
        from videobrief.application.compatibility import normalize_brief_for_read

        cases = [
            ("evidence_store", True),
            ("evidence_store", ["bad"]),
            ("evidence_store", [{}]),
            ("content_model", True),
            ("content_model", {"template": "tutorial", "items": True}),
            ("decision_brief", "spoof"),
            ("decision_brief", {"answer": "incomplete"}),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                raw = copy.deepcopy(LEGACY)
                raw[field] = value
                projected = normalize_brief_for_read(raw)
                self.assertIsInstance(projected["evidence_store"], list)
                self.assertIsInstance(projected["content_model"], dict)
                self.assertIsInstance(projected["decision_brief"], dict)
                self.assertEqual(normalize_brief_for_read(projected), projected)

    def test_all_supported_generations_reach_one_canonical_idempotent_shape(self):
        from videobrief.application.compatibility import detect_brief_generation, normalize_brief_for_read

        evidence = {
            "evidence_id": "E0001", "time": "00:00", "seconds": 0, "end_seconds": 5,
            "quote": "证据", "source": "transcript",
        }
        evidence_v1 = copy.deepcopy(LEGACY)
        evidence_v1["evidence_store"] = [evidence]
        typed_v2 = copy.deepcopy(evidence_v1)
        typed_v2["content_model"] = {
            "template": "tutorial",
            "items": [{
                "role": "step", "title": "步骤", "detail": "执行步骤", "evidence_ids": ["E0001"],
            }],
        }
        decision_v3 = copy.deepcopy(typed_v2)
        decision_v3["decision_brief"] = {
            "question": "怎么做？", "answer": "执行步骤", "takeaways": [],
            "watch_verdict": "直接阅读即可", "watch_reason": "无需画面", "watch_seconds": 0,
        }

        self.assertEqual(detect_brief_generation({"evidence_store": []}), "legacy-no-store")
        self.assertEqual(detect_brief_generation({"evidence_store": True}), "legacy-no-store")
        self.assertEqual(detect_brief_generation(evidence_v1), "evidence-store-v1")
        self.assertEqual(detect_brief_generation(typed_v2), "typed-v2")
        self.assertEqual(detect_brief_generation(decision_v3), "decision-v3")

        for payload in [LEGACY, evidence_v1, typed_v2, decision_v3]:
            with self.subTest(generation=detect_brief_generation(payload)):
                projected = normalize_brief_for_read(payload)
                self.assertEqual(normalize_brief_for_read(projected), projected)
                self.assertEqual(projected["compatibility"], {
                    "source_generation": "canonical-v4",
                    "detected_generation": detect_brief_generation(payload),
                    "projected": True,
                    "stored_payload_unchanged": True,
                })

        spoofed = copy.deepcopy(decision_v3)
        spoofed["compatibility"] = {
            "source_generation": "legacy-no-store", "projected": True,
            "stored_payload_unchanged": True,
        }
        self.assertEqual(
            normalize_brief_for_read(spoofed)["compatibility"]["source_generation"],
            "canonical-v4",
        )

    def test_modern_evidence_ids_remain_byte_for_byte_stable(self):
        from videobrief.application.compatibility import normalize_brief_for_read

        modern = copy.deepcopy(LEGACY)
        modern["evidence_store"] = [
            {"evidence_id": "E0042", "time": "01:20", "seconds": 80, "end_seconds": 84,
             "quote": "字段太多会增加录入阻力。", "source": "transcript"}
        ]
        modern["chapters"][0]["evidence"][0]["evidence_id"] = "E0042"
        projected = normalize_brief_for_read(modern)
        self.assertEqual(projected["evidence_store"], modern["evidence_store"])


if __name__ == "__main__":
    unittest.main()
