"""Reviewed official stream thumbnails plus explicit NUROJUNK host titles."""
import re

CHANNEL = 'UCuvYHCPdMxfvjW_F9w5LmRA'
# Individual review of the official thumbnails, 2026-11-22. No face recognition
# is performed on future uploads. Ambiguous older art stays unassigned.
REVIEWED = {
 'kagura': ['LCm2TfytMf4','IRLrX-TywKU','G5DZ2kH8mTo','adtFJVZxC58','lev_1Zx4M9U',
            'Kjlzh_9ZtEA','3IotcByyuNI','3X9sM4wEjyY','r3H_ez8n5UI','6u2__SPJvR4','ejsB4ykf0Yk','50GLA4lsEfg',
            'Tnmfjk-3JQo','xhiU2AtFI-c'],
 'sakuya': ['rgL4trzJ-14','KQWUU1JUE2E','alJrUevkhzg','eidHW9GJAYA','hv1i8BVy7Us','hh-c-vz-UdI',
            'YYMPs9j21Hk','7yevdzRJcNQ','y7Itq1ytVxU','6QuQGtGNYDw','Tnmfjk-3JQo','xhiU2AtFI-c'],
}


def memberships(videos):
    result={slug:list(ids) for slug,ids in REVIEWED.items()}
    for v in videos:
        if v.channel_id!=CHANNEL or not v.started_at:
            continue
        # Titles naming the stream host, not generic social/merch boilerplate.
        for slug,tokens in [('sakuya','SAKUYA|サクヤ'),('kagura','KAGURA|カグラ')]:
            if re.search(rf'(?:【|\[)(?:{tokens})(?!\w)|NUROJUNK[ /　-]+(?:{tokens})(?!\w)|(?:】|\])(?:{tokens})[、,]',v.title,re.I):
                result[slug].append(v.id)
    return {'channel_id':CHANNEL,'playlists':{s:sorted(set(ids)) for s,ids in result.items()},'basis':'reviewed_thumbnails_and_explicit_titles'}
