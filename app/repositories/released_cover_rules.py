"""Released covers among stored recordings (alias ``r``), kept out of original-song lists.

A recording counts as a released cover when its title/version marks it as one, or when its
song credits only other artists: none of the recording's singers, nor their groups/members.
Recordings without a song link or song credits are not judged here (unknown stays original).
The discography (albums) still lists these recordings; only original-song views exclude them.
"""

RELEASED_COVER_SQL = """(
  concat_ws(' ', r.title_native, r.version_label) ~* :released_cover_marker
  OR (r.song_id IS NOT NULL
    AND EXISTS (SELECT 1 FROM song_artists rc_credit WHERE rc_credit.song_id = r.song_id)
    AND NOT EXISTS (
      SELECT 1 FROM song_artists rc_credit
      JOIN recording_artists rc_singer ON rc_singer.recording_id = r.id
      LEFT JOIN artist_group_members rc_group
        ON rc_group.member_id = rc_singer.artist_id OR rc_group.group_id = rc_singer.artist_id
      WHERE rc_credit.song_id = r.song_id
        AND rc_credit.artist_id IN (rc_singer.artist_id, rc_group.group_id, rc_group.member_id))))"""

# "Cover", "Covered", "Cover Live", "カバー", "歌ってみた"; word bounds keep "Undercover" original.
RELEASED_COVER_PARAMS = {'released_cover_marker': r'(\mcover(ed)?\M|カバー|歌ってみた)'}
