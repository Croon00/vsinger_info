"""User-approved shared channels; never infer ownership from matching names."""
import json
import re


RULES = [
    dict(group_slug='vesperbell', member_slug='vesperbell-yomi', tokens=['YOMI','ヨミ','요미'], compact='YOMI'),
    dict(group_slug='vesperbell', member_slug='vesperbell-kasuka', tokens=['KASUKA','カスカ','카스카'], compact='KASUKA'),
    dict(group_slug='kmnz', member_slug='kmnz-lita', tokens=['LITA','리타'], compact='LITA'),
    dict(group_slug='kmnz', member_slug='kmnz-tina', tokens=['TINA','티나'], compact='TINA'),
    dict(group_slug='kmnz', member_slug='kmnz-nero', tokens=['NERO','네로'], compact='NERO'),
]

for rule in RULES:
    rule['channel_id'] = ('UCwuS0uY-Z2Gr_5OV2oFybFA' if rule['group_slug']=='kmnz' else 'UCPd0Z22gF43dUidPYEQO5-w')
    tokens = '|'.join(re.escape(token) for token in rule['tokens'])
    all_tokens = '|'.join(re.escape(t) for r in RULES if r['group_slug']==rule['group_slug'] for t in r['tokens'])
    group = re.escape(rule['group_slug'])
    first = rf'{group}[ _　-]*({tokens})([^a-z0-9]|$)'
    bracket = rf'(【|\[)\s*({tokens})\s*(】|\])'
    by = rf'covered\s+by[ _　-]*({tokens})'
    following = rf'{group}[ _　-]*({all_tokens})([^a-z0-9]|$)[^#\r\n]*'
    rule['title_pattern'] = rf'{first}|{bracket}|{by}([^[:alnum:]_]|$)|{following}(^|[^[:alnum:]_])({tokens})([^[:alnum:]_]|$)'
    rule['python_pattern'] = rf'{first}|{bracket}|{by}(?!\w)|{following}(?<!\w)({tokens})(?!\w)'
    # A title explicitly naming someone outside the approved current set is
    # not evidence that all three approved members sang it.
    rule['other_pattern'] = r'KMNZ[ _　-]+LIZ([^a-z0-9]|$)' if rule['group_slug']=='kmnz' else r'(?!)'

for rule in RULES:
    rule['any_member_pattern'] = '|'.join(r['title_pattern'] for r in RULES if r['group_slug']==rule['group_slug'])
    rule['all_named_pattern'] = '|'.join(r['title_pattern'] for r in RULES)

# Exact source IDs verified in the primary channel's uploads playlist and
# videos.list. Subscriber statistics continue to use the primary channel only.
COVER_SOURCE_CHANNELS = {
    'kmnz': ['UCwuS0uY-Z2Gr_5OV2oFybFA', 'UC3cuxhq3Cv-9h5wNXvWHspg',
             'UCqSPZz3gDBxJP-xaME8w-yA', 'UCnwnKd78qy2Txjs1WlfwkxA',
             'UCsT7GTwoXE0tatNnDhcE58Q', 'UCRMpIxnySp7Fy5SbZ8dBv2w'],
    'vesperbell': ['UCPd0Z22gF43dUidPYEQO5-w', 'UCjGsOnj8SPL7CWVTgXDmm3g',
                   'UCREUB-PjfMdI0KziJy-u0TQ'],
}

SHARED_PARAMS = {'shared_rules': json.dumps([
    {**r, 'channel_id': channel, 'is_statistics_source': channel == r['channel_id']}
    for r in RULES for channel in COVER_SOURCE_CHANNELS[r['group_slug']]
],ensure_ascii=True)}

SHARED_MEMBERS_CTE = """shared_members AS MATERIALIZED (
  SELECT g.id group_id,g.name_native group_name,a.id member_id,e.id account_id,
    ae.position,ae.id link_id,r.title_pattern,r.other_pattern,r.any_member_pattern,r.all_named_pattern,r.is_statistics_source
  FROM jsonb_to_recordset(CAST(:shared_rules AS jsonb))
    r(group_slug text,member_slug text,title_pattern text,other_pattern text,any_member_pattern text,all_named_pattern text,channel_id text,is_statistics_source boolean)
  JOIN artists g ON g.slug=r.group_slug AND g.archived_at IS NULL
  JOIN artist_group_members gm ON gm.group_id=g.id AND gm.left_on IS NULL
  JOIN artists a ON a.id=gm.member_id AND a.slug=r.member_slug AND a.archived_at IS NULL AND a.show_in_catalog
  JOIN artist_external_accounts ae ON ae.artist_id=g.id AND ae.relationship='owner'
  JOIN external_accounts e ON e.id=ae.account_id AND e.platform='youtube' AND e.platform_id=r.channel_id AND e.archived_at IS NULL
)"""

COVER_CREDITS_CTE = SHARED_MEMBERS_CTE + """,
  named_members AS MATERIALIZED (
    SELECT DISTINCT c.id cover_id,sm.member_id,sm.group_id
    FROM covers c JOIN videos v ON v.id=c.video_id
    CROSS JOIN shared_members sm
    WHERE c.archived_at IS NULL AND v.archived_at IS NULL AND v.title ~* sm.title_pattern
      AND EXISTS(SELECT 1 FROM shared_members source WHERE source.account_id=v.source_account_id)
  ), cover_credits AS (
    SELECT c.id cover_id,ae.artist_id FROM covers c JOIN videos v ON v.id=c.video_id
    JOIN external_accounts e ON e.id=v.source_account_id AND e.archived_at IS NULL
    JOIN artist_external_accounts ae ON ae.account_id=e.id AND ae.relationship='owner'
    WHERE c.archived_at IS NULL AND v.archived_at IS NULL
    UNION
    SELECT nm.cover_id,nm.member_id FROM named_members nm
    UNION
    SELECT c.id,sm.member_id FROM covers c JOIN videos v ON v.id=c.video_id
    JOIN shared_members sm ON sm.account_id=v.source_account_id
    WHERE c.archived_at IS NULL AND v.archived_at IS NULL
      AND NOT EXISTS(SELECT 1 FROM named_members nm WHERE nm.cover_id=c.id)
      AND v.title !~* sm.other_pattern AND v.title !~* sm.all_named_pattern
  )"""


def members_for_title(group_slug, title):
    """Reference policy used by fixture tests; SQL applies it before pagination."""
    rules = [r for r in RULES if r['group_slug']==group_slug]
    if not rules:
        return set()
    matched = set()
    for rule in RULES:
        if re.search(rule['python_pattern'], title, re.I):
            matched.add(rule['member_slug'])
    if matched:
        return matched
    if rules and re.search(rules[0]['other_pattern'],title,re.I):
        return set()
    return {r['member_slug'] for r in rules}
