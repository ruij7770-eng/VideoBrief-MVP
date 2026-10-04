import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace


class AnalyseCommandTests(unittest.TestCase):
    def test_exactly_one_input_source_is_required(self):
        from videobrief.application.commands import AnalyseCommand
        from videobrief.domain.errors import InputValidationError

        with self.assertRaises(InputValidationError):
            AnalyseCommand()
        with self.assertRaises(InputValidationError):
            AnalyseCommand(url="https://youtu.be/abc", transcript="重复输入")


class SourceRegistryTests(unittest.TestCase):
    def test_bilibili_audio_fallback_accepts_string_or_list(self):
        from videobrief.infrastructure.sources.bilibili import _first_audio_url

        self.assertEqual(_first_audio_url({"backupUrl": "https://audio.example/one"}), "https://audio.example/one")
        self.assertEqual(_first_audio_url({"backup_url": ["https://audio.example/two"]}), "https://audio.example/two")

    def test_url_classification_uses_exact_host_allowlist(self):
        from videobrief.infrastructure.sources.registry import classify_url

        self.assertEqual(classify_url("https://www.bilibili.com/video/BV1234567890"), "bilibili")
        self.assertEqual(classify_url("https://b23.tv/abc"), "bilibili")
        self.assertEqual(classify_url("https://youtu.be/abc"), "youtube")
        self.assertEqual(classify_url("https://evilbilibili.com/video/BV1234567890"), "unsupported")

    def test_registry_prefers_pasted_transcript(self):
        from videobrief.application.commands import AnalyseCommand
        from videobrief.infrastructure.sources.registry import SourceRegistry

        adapter = SourceRegistry.default().resolve(AnalyseCommand(transcript="[00:00] 内容"))
        self.assertEqual(adapter.kind, "pasted_transcript")

    def test_youtube_falls_back_when_yt_dlp_process_is_missing(self):
        from videobrief.application.commands import AnalyseCommand
        from videobrief.infrastructure.sources.youtube import YouTubeSource

        def missing_runner(*_args, **_kwargs):
            raise FileNotFoundError("yt-dlp missing")

        source = YouTubeSource(
            runner=missing_runner,
            transcript_fetcher=lambda _video_id: [SimpleNamespace(start=12.0, text="备用字幕")],
        )
        result = source.acquire(AnalyseCommand(url="https://youtu.be/abc123XYZ89"))
        self.assertEqual(result.rows, [{"time": "00:12", "body": "备用字幕"}])

    def test_yt_dlp_command_points_to_a_real_executable_when_available(self):
        from videobrief.infrastructure.sources.youtube import yt_dlp_command

        command = yt_dlp_command()
        self.assertTrue(Path(command).exists() or shutil.which(command), command)


if __name__ == "__main__":
    unittest.main()
