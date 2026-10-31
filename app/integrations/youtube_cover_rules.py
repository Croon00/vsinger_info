"""Conservative cover eligibility. Descriptions and vocal credits are not proof."""
import re

COVER_TITLE_PATTERN = r'(?<![a-z])cover(?:ed|s)?(?![a-z])|歌ってみた|カバー|커버'
SELF_COVER_PATTERN = r'self[\s_-]*cover|セルフ[\s・_-]*カバー|셀프\s*커버'


def is_cover_title(title: str) -> bool:
    return bool(re.search(COVER_TITLE_PATTERN, title, re.I)) and not bool(re.search(SELF_COVER_PATTERN, title, re.I))
