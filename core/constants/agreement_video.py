import json
from pathlib import Path

_FORMATS_PATH = Path(__file__).with_name("agreement_video_formats.json")

with _FORMATS_PATH.open(encoding="utf-8") as handle:
	_DATA = json.load(handle)

AGREEMENT_VIDEO_EXTENSIONS = frozenset(
	ext.strip().lower() for ext in _DATA.get("extensions", []) if ext
)


def agreement_video_file_extension(filename: str) -> str:
	base = (filename or "").strip().replace("\\", "/").split("/")[-1]
	if "." not in base:
		return ""
	return base.rsplit(".", 1)[-1].lower()


def is_agreement_video_file(filename: str, content_type: str | None = None) -> bool:
	mime = (content_type or "").split(";", 1)[0].strip().lower()
	if mime.startswith("video/"):
		return True
	ext = agreement_video_file_extension(filename)
	return ext in AGREEMENT_VIDEO_EXTENSIONS
