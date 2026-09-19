from copy import deepcopy

import pytest

from app.core.artist_identity import (
    artist_name_aliases, display_artist_name, group_artists, identities,
    normalize_artist_display_names, find_preset_artist,
)


@pytest.mark.parametrize('name,label,expected', [
    ('MIKAGE', None, '深影 (MIKAGE)'),
    ('深影', '深影', '深影 (MIKAGE)'),
    ('ASU', 'ASU (明透)', '明透 (ASU)'),
    ('花譜', '花譜 / KAF', '花譜 (KAF)'),
    ('Setono_Toto', None, '瀬戸乃 とと (Setono Toto)'),
    ('HACHI', 'HACHI', 'HACHI'),
    ('OTHER', '別名', '別名 (OTHER)'),
    ('別名', 'OTHER (別名)', '別名 (OTHER)'),
    ('カタカナ', None, 'カタカナ'),
    ('未知', None, '未知'),
])
def test_display_format(name, label, expected):
    assert display_artist_name(name, label) == expected
    assert display_artist_name(name, expected) == expected


def test_every_catalogue_label_is_idempotent():
    for identity in identities():
        for alias in identity['aliases']:
            assert display_artist_name(alias, None, identity['agency']) == identity['display_name']
        assert display_artist_name(identity['display_name']) == identity['display_name']


def test_grouping_preserves_all_source_ids_profiles_and_owners_without_mutation():
    rows = [
        {'id': 16, 'name': 'MIKAGE', 'agency': 'RK Music', 'discord_user_id': 'system:rkmusic',
         'show_in_youtube_lives': True, 'sources': [{'id': 16, 'artist_id': 16, 'value': 'Mikage_0916'}]},
        {'id': 54, 'name': '深影', 'agency': 'RK Music', 'discord_user_id': 'owner',
         'profile_intro': 'profile', 'show_in_youtube_lives': False,
         'sources': [{'id': 79619, 'artist_id': 54, 'value': 'Mikage_0916'}]},
    ]
    before = deepcopy(rows)
    result = group_artists(rows)
    assert rows == before
    assert len(result) == 1
    assert result[0]['related_artist_ids'] == [16, 54]
    assert result[0]['profile_intro'] == 'profile'
    assert result[0]['show_in_youtube_lives'] is True
    assert [s['id'] for s in result[0]['sources']] == [16, 79619]
    assert [s['artist_id'] for s in result[0]['sources']] == [16, 54]


def test_different_agencies_and_unconfirmed_names_are_not_collapsed():
    rows = [{'id': 1, 'name': 'MIKAGE', 'agency': 'Another agency'},
            {'id': 2, 'name': '深影', 'agency': 'RK Music'},
            {'id': 3, 'name': 'UNKNOWN'}, {'id': 4, 'name': 'UNKNOWN'}]
    assert len(group_artists(rows)) == 4


def test_spotify_matched_registration_stays_addressable():
    rows = [{'id': 1, 'name': '深影', 'spotify_artist_id': None},
            {'id': 2, 'name': 'MIKAGE', 'spotify_artist_id': 'spotify-id'}]
    assert group_artists(rows)[0]['id'] == 2


def test_archive_aliases_cover_native_english_and_legacy_names():
    assert {'深影', 'MIKAGE'} <= set(artist_name_aliases('深影 (MIKAGE)'))
    assert 'Setono_Toto' in artist_name_aliases('瀬戸乃とと')


def test_normalization_dry_run_does_not_write_and_apply_only_updates_labels():
    class Connection:
        def __init__(self): self.calls = []
        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            return self
        def fetchall(self):
            return [{'id': 1, 'name': 'MIKAGE', 'display_name': None, 'agency': 'RK Music'}]
    conn = Connection()
    assert len(normalize_artist_display_names(conn)) == 1
    assert len(conn.calls) == 1
    normalize_artist_display_names(conn, apply=True)
    assert conn.calls[-1][1] == ('深影 (MIKAGE)', 1)
    assert conn.calls[-1][0].startswith('UPDATE artists SET display_name')


def test_preset_lookup_scopes_owners_and_checks_both_name_variants():
    class Connection:
        def execute(self, sql, params):
            assert 'discord_user_id = %s' in sql
            assert 'discord_user_id IS NULL AND agency = %s' in sql
            assert params[0] == 'system:rkmusic'
            assert {'mikage', '深影'} <= set(params[4])
            return self
        def fetchone(self): return {'id': 16}
    assert find_preset_artist(Connection(), 'system:rkmusic', '深影', 'RK Music') == {'id': 16}


def test_event_filter_expands_either_legacy_artist_id():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services.artist_service import ArtistService
    service = ArtistService(Mock())
    service.artists.list = Mock(return_value=[
        SimpleNamespace(id=16, name='MIKAGE', display_name=None, agency='RK Music'),
        SimpleNamespace(id=54, name='深影', display_name=None, agency='RK Music'),
    ])
    service.events.list = Mock(return_value=[])
    for artist_id in (16, 54):
        service.list_event_candidates(artist_id=artist_id, event_type='live_event')
        service.events.list.assert_called_with(artist_id=[16, 54], event_type='live_event')
