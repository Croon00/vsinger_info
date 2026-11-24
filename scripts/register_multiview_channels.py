"""Register the two approved YouTube membership channels for multiview."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.catalog_session import CatalogIdentityError, catalog_runtime_session


CHANNELS = (
    ("vesperbell", "UCIZdHFI1j5glJBzYJrH99pw", "VESPERBELL_MEMBERSHIP", "VESPERBELL MEMBERSHIP"),
    ("kmnz", "UC68J5pWEshmwhDH45qnpIsg", "KMNZ", "KMNCLUB"),
)


def register(session):
    for slug, channel_id, handle, label in CHANNELS:
        values = dict(slug=slug, channel=channel_id, handle=handle,
                      url=f"https://www.youtube.com/@{handle}", label=label)
        artist_id = session.execute(text("""SELECT id FROM artists
            WHERE slug=:slug AND entity_kind='group' AND archived_at IS NULL FOR UPDATE"""),
            values).scalar_one_or_none()
        if artist_id is None:
            raise ValueError(f"활성 그룹을 찾을 수 없습니다. ({slug})")
        session.execute(text("""INSERT INTO external_accounts(platform,platform_id,handle,url,collection_enabled)
            VALUES ('youtube',:channel,:handle,:url,false) ON CONFLICT (platform,platform_id) DO NOTHING"""), values)
        account = session.execute(text("""SELECT id,archived_at FROM external_accounts
            WHERE platform='youtube' AND platform_id=:channel FOR UPDATE"""), values).one()
        if account.archived_at is not None:
            raise ValueError(f"보관된 계정입니다. ({slug})")
        values.update(artist=artist_id, account=account.id)
        links = session.execute(text("""SELECT artist_id,relationship FROM artist_external_accounts
            WHERE account_id=:account AND (relationship='owner' OR artist_id=:artist)"""), values).all()
        if any(link.artist_id != artist_id or link.relationship != 'owner' for link in links):
            raise ValueError(f"기존 계정 소유권과 충돌합니다. ({slug})")
        session.execute(text("""INSERT INTO artist_external_accounts
            (artist_id,account_id,relationship,is_primary,label,position)
            SELECT :artist,:account,'owner',false,:label,COALESCE(max(position)+1,0)
            FROM artist_external_accounts WHERE artist_id=:artist
            ON CONFLICT (artist_id,account_id) DO NOTHING"""), values)
        session.execute(text("""INSERT INTO collection_states(external_account_id,provider_state)
            VALUES (:account,'{"youtube_live_only": true}'::jsonb)
            ON CONFLICT (external_account_id) DO UPDATE SET
                provider_state=collection_states.provider_state || EXCLUDED.provider_state
            WHERE NOT (collection_states.provider_state @> EXCLUDED.provider_state)"""), values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    try:
        with catalog_runtime_session() as session:
            register(session)
    except (CatalogIdentityError, SQLAlchemyError) as exc:
        print(f"통합 DB 등록 실패 ({type(exc).__name__})", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("멀티뷰 수집 대상 확인 완료: VESPERBELL MEMBERSHIP, KMNCLUB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
