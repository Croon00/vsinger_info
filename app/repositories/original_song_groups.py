"""User-selected original-song display groups; no persisted credit changes."""
ORIGINAL_GROUPS_CTE = """original_groups AS MATERIALIZED (
  SELECT g.id group_id,g.name_native group_name,g.name_ko group_name_ko,
    g.name_latin group_name_latin,a.id member_id
  FROM (VALUES
    ('vesperbell','vesperbell-yomi'),('vesperbell','vesperbell-kasuka'),
    ('kmnz','kmnz-lita'),('kmnz','kmnz-tina'),('kmnz','kmnz-nero'),
    ('honk-the-horn','moco'),('honk-the-horn','bambi'),
    ('nurojunk','kagura'),('nurojunk','sakuya')
  ) rules(group_slug,member_slug)
  JOIN artists g ON g.slug=rules.group_slug AND g.archived_at IS NULL
  JOIN artist_group_members gm ON gm.group_id=g.id AND gm.left_on IS NULL
  JOIN artists a ON a.id=gm.member_id AND a.slug=rules.member_slug
    AND a.archived_at IS NULL AND a.show_in_catalog
)"""
