from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings
from test_catalog_migration import apply, database, local_server, row


def test_editor_requires_a_separate_key(monkeypatch):
    monkeypatch.setattr(settings, 'api_key', 'read-key')
    monkeypatch.setattr(settings, 'lyrics_editor_key', None)
    with TestClient(app) as client:
        path = '/api/recordings/1/lyrics'
        draft = {'version': None, 'original_lyrics': 'Fixture text'}
        assert client.put(path, json=draft).status_code == 401
        headers = {'X-API-Key': 'read-key'}
        assert client.put(path, json=draft, headers=headers).status_code == 503
        monkeypatch.setattr(settings, 'lyrics_editor_key', 'edit-key')
        assert client.put(path, json=draft, headers=headers).status_code == 403
        headers['X-Lyrics-Editor-Key'] = 'edit-key'
        assert client.put(path, json=draft | {'original_lyrics': '\r\n '}, headers=headers).status_code == 422
        assert client.put(path, json=draft | {'lyrics_source_url': 'javascript:alert(1)'}, headers=headers).status_code == 422


def test_editor_registers_edits_and_keeps_history(database, monkeypatch):
    apply(database)
    info = database.info
    monkeypatch.setattr(settings, 'database_url', f'postgresql://catalog_test@127.0.0.1:{info.port}/{info.dbname}')
    monkeypatch.setattr(settings, 'new_database_instance_id', None)
    monkeypatch.setattr(settings, 'api_key', None)
    monkeypatch.setattr(settings, 'lyrics_editor_key', 'edit-key')
    artist = row(database, 'artists', slug='fixture', entity_kind='solo', name_native='Fixture artist', show_in_catalog=True)
    ids = []
    for title in ('Fixture original', 'Fixture cover', 'Fixture archived lyrics'):
        recording = row(database, 'recordings', title_native=title)
        row(database, 'recording_artists', recording_id=recording, artist_id=artist, role='primary')
        ids.append(recording)
    recording, cover, archived = ids
    starting_version = database.execute('SELECT version FROM recordings WHERE id=%s', (recording,)).fetchone()[0]
    row(database, 'recording_lyrics', recording_id=archived, original_lyrics='Archived')
    database.execute('UPDATE recording_lyrics SET archived_at=CURRENT_TIMESTAMP WHERE recording_id=%s', (archived,))
    database.commit()

    with TestClient(app, headers={'X-Lyrics-Editor-Key': 'edit-key'}) as client:
        path = f'/api/recordings/{recording}/lyrics'
        draft = {'version': None, 'original_lyrics': 'First\r\n\r\nSecond',
                 'pronunciation_ko': '퍼스트\n\n세컨드', 'lyrics_source_url': 'https://example.com/source'}
        missing = client.get(path)
        assert missing.status_code == 404, missing.text
        songs_path = '/api/explore/songs?kind=original&q=Fixture%20original'
        [before] = client.get(songs_path).json()['items']
        assert before['recording_id'] == recording and before['lyrics_recording_id'] is None
        cover_response = client.put(f'/api/recordings/{cover}/lyrics', json=draft)
        assert cover_response.status_code == 404, cover_response.text
        archived_response = client.put(f'/api/recordings/{archived}/lyrics', json=draft)
        assert archived_response.status_code == 409, archived_response.text
        created = client.put(path, json=draft)
        assert created.status_code == 200, created.text
        assert created.json()['version'] == 1 and created.json()['original_lyrics'] == 'First\n\nSecond'
        assert client.put(path, json=draft).json() == created.json()
        [after] = client.get(songs_path).json()['items']
        assert after['lyrics_recording_id'] == recording

        update = draft | {'version': 1, 'translation_ko': '첫째\n\n둘째'}
        edited = client.put(path, json=update)
        assert edited.status_code == 200, edited.text
        assert edited.json()['version'] == 2
        assert client.put(path, json=update | {'original_lyrics': 'Stale edit'}).status_code == 409
        assert client.get(path).json() == edited.json()
        edited_source = client.put(path, json=update | {'version': 2, 'original_lyrics': 'Corrected',
                                                       'lyrics_source_url': 'https://example.com/corrected'})
        assert edited_source.status_code == 200, edited_source.text
        assert edited_source.json()['lyrics_source_url'] == 'https://example.com/corrected'

    assert database.execute('SELECT version FROM recordings WHERE id=%s', (recording,)).fetchone() == (starting_version + 3,)
    assert database.execute('SELECT count(*) FROM source_documents').fetchone() == (2,)
    assert database.execute("""SELECT action,before_data->>'original_lyrics',after_data->>'original_lyrics'
        FROM catalog_changes WHERE entity_type='recording_lyrics' ORDER BY id""").fetchall() == [
            ('create', None, 'First\n\nSecond'),
            ('update', 'First\n\nSecond', 'First\n\nSecond'),
            ('update', 'First\n\nSecond', 'Corrected'),
        ]
