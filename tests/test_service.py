import unittest

from videobrief_service import extract_youtube_id, parse_timestamped_transcript, source_kind, to_simplified, yt_dlp_command


class YouTubeUrlTests(unittest.TestCase):
    def test_extracts_watch_url_id(self):
        self.assertEqual(extract_youtube_id("https://www.youtube.com/watch?v=abc123XYZ89"), "abc123XYZ89")

    def test_extracts_short_url_id(self):
        self.assertEqual(extract_youtube_id("https://youtu.be/abc123XYZ89?t=12"), "abc123XYZ89")


class SimplifiedChineseTests(unittest.TestCase):
    def test_converts_traditional_whisper_output_to_simplified(self):
        self.assertEqual(
            to_simplified("我發布了教學視頻，這個功能能幫助使用者快速理解內容。"),
            "我发布了教学视频，这个功能能帮助使用者快速理解内容。",
        )


class SourceKindTests(unittest.TestCase):
    def test_detects_bilibili_video_url(self):
        self.assertEqual(source_kind("https://www.bilibili.com/video/BV1xx411c7mD"), "bilibili")

    def test_detects_local_filename(self):
        self.assertEqual(source_kind("lecture.mp4"), "local")


class YtDlpTests(unittest.TestCase):
    def test_resolves_an_executable_command(self):
        self.assertTrue(yt_dlp_command())


class TranscriptTests(unittest.TestCase):
    def test_parses_vtt_and_removes_cue_metadata(self):
        source = """WEBVTT

00:00:01.000 --> 00:00:04.000 align:start position:0%
第一段内容

00:01:05.000 --> 00:01:08.000
第二段内容
"""
        rows = parse_timestamped_transcript(source)
        self.assertEqual(rows, [
            {"time": "00:01", "body": "第一段内容"},
            {"time": "01:05", "body": "第二段内容"},
        ])


if __name__ == "__main__":
    unittest.main()
