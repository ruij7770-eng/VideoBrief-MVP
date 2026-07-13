"""Transcribe a Bilibili video and save result for testing."""
import sys, json
sys.path.insert(0, "C:\\Users\\30658\\VideoBrief-MVP")

import videobrief_bilibili
from videobrief_service import make_brief

rows = videobrief_bilibili.bilibili_transcribe("https://www.bilibili.com/video/BV1cmTu6mEL3")
result = make_brief(rows)
result["source"] = "bilibili_transcribe"
result["url"] = "https://www.bilibili.com/video/BV1cmTu6mEL3"

with open("C:\\Users\\30658\\VideoBrief-MVP\\_test_bili_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"DONE: {result['title']} | {len(result['chapters'])} chapters | {result['source_rows']} rows")
