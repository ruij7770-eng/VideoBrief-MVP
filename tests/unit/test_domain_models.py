import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError


class DomainContractTests(unittest.TestCase):
    def test_decision_brief_allows_at_most_three_takeaways(self):
        from videobrief.domain.models import DecisionBrief, Insight

        insight = Insight(title="结论", detail="详情", evidence_ids=["E0001"])
        with self.assertRaises(ValidationError):
            DecisionBrief(
                question="问题",
                answer="答案",
                takeaways=[insight, insight, insight, insight],
                watch_verdict="not_required",
            )

    def test_insight_requires_at_least_one_evidence_id(self):
        from videobrief.domain.models import Insight

        with self.assertRaises(ValidationError):
            Insight(title="无证据", detail="不能进入页面", evidence_ids=[])

    def test_brief_rejects_unknown_evidence_references(self):
        from videobrief.domain.models import Brief, DecisionBrief, Evidence, Insight

        with self.assertRaises(ValidationError):
            Brief(
                title="示例",
                summary="摘要",
                source="pasted_transcript",
                evidence_store=[Evidence(evidence_id="E0001", time="00:00", seconds=0, quote="原文")],
                key_insights=[Insight(title="错误", detail="引用不存在", evidence_ids=["E9999"])],
                decision_brief=DecisionBrief(question="问题", answer="答案", watch_verdict="not_required"),
            )

    def test_brief_serializes_legacy_shape(self):
        from videobrief.domain.models import Brief, DecisionBrief, Evidence

        brief = Brief(
            title="示例",
            summary="摘要",
            source="pasted_transcript",
            evidence_store=[Evidence(evidence_id="E0001", time="00:00", seconds=0, quote="原文")],
            decision_brief=DecisionBrief(question="问题", answer="答案", watch_verdict="not_required"),
        )
        payload = brief.model_dump(mode="json")
        self.assertEqual(payload["schema_version"], 4)
        self.assertEqual(payload["evidence_store"][0]["quote"], "原文")


class SettingsTests(unittest.TestCase):
    def test_public_agent_status_never_contains_key(self):
        from videobrief.config import Settings

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-value"}, clear=True):
            settings = Settings.from_env()
        status = settings.agent_status()
        self.assertTrue(status["configured"])
        self.assertNotIn("api_key", status)
        self.assertNotIn("secret-value", repr(status))


if __name__ == "__main__":
    unittest.main()
