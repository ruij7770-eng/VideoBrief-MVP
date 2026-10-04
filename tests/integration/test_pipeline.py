import unittest

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import AcquisitionResult


class FakeSource:
    kind = "fake"

    def acquire(self, command, progress=None):
        return AcquisitionResult(
            rows=[
                {"time": "00:00", "body": "第一步建立唯一入口。"},
                {"time": "01:00", "body": "总结：只保留必要字段。"},
            ],
            source="pasted_transcript",
        )


class FakeRegistry:
    def resolve(self, command):
        return FakeSource()


class SmartOverride:
    def enhance(self, rows, brief, mode):
        result = __import__("copy").deepcopy(brief)
        result["quick_brief"] = {
            "central_question": "怎样降低录入阻力？",
            "direct_answer": "智能答案：只保留必要字段。",
            "why_it_matters": "更容易坚持。",
            "limitation": "未说明统一数量。",
            "evidence_ids": ["E0002"],
        }
        result["agent"] = {"mode": "smart"}
        return result


class UnderstandingPipelineTests(unittest.TestCase):
    def test_pipeline_finalizes_decision_after_smart_enhancement(self):
        from videobrief.application.pipeline import UnderstandingPipeline
        from videobrief.infrastructure.analysis.semantic import make_brief

        events = []
        pipeline = UnderstandingPipeline(registry=FakeRegistry(), local_analyzer=make_brief, smart_analyzer=SmartOverride())
        result = pipeline.run(
            AnalyseCommand(transcript="[00:00] 输入", analysis_mode="smart"),
            lambda stage, progress, message: events.append((stage, progress, message)),
        )
        self.assertEqual(result["decision_brief"]["answer"], "智能答案：只保留必要字段。")
        self.assertEqual(result["source"], "pasted_transcript")
        self.assertEqual(result["schema_version"], 4)
        self.assertEqual([stage for stage, _, _ in events], [
            "acquiring", "normalizing", "structuring", "enhancing", "auditing", "finalizing"
        ])

    def test_pipeline_output_satisfies_domain_evidence_invariants(self):
        from videobrief.application.pipeline import UnderstandingPipeline
        from videobrief.domain.models import Brief
        from videobrief.infrastructure.analysis.semantic import make_brief

        result = UnderstandingPipeline(registry=FakeRegistry(), local_analyzer=make_brief, smart_analyzer=SmartOverride()).run(
            AnalyseCommand(transcript="[00:00] 输入", analysis_mode="smart")
        )
        Brief.model_validate(result)


if __name__ == "__main__":
    unittest.main()
