from app.integrations.youtube_cover_rules import COVER_TITLE_PATTERN, SELF_COVER_PATTERN

COVER_TITLE_SQL = "v.title ~* :cover_title_marker AND v.title !~* :self_cover_marker"
COVER_TITLE_PARAMS = dict(cover_title_marker=COVER_TITLE_PATTERN, self_cover_marker=SELF_COVER_PATTERN)
