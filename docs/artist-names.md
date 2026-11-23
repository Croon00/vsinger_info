# 아티스트 이름과 식별

최종 확인 2026-11-23. 아티스트 이름·별칭을 어떻게 저장하고 조회하는지와, 이름만으로 데이터를 합치지 않는 원칙을 정리한다. 조회 계약은 [조회 API](read-api.md), 남은 작업은 [후속 작업](backend-roadmap.md)을 따른다.

## 현재 기준 (신규 DB)

- 아티스트 한 명은 `artists` 한 행이다. 이름은 원어 `name_native`, 한국어 `name_ko`, 영문 `name_latin`으로 나눠 저장하고, 그 밖의 표기는 `artist_aliases`에 둔다. 필드 설명은 [카탈로그 테이블·필드](catalog-schema.md)에 있다.
- `GET /api/artists`의 응답에서 `name`은 `name_native`, `display_name`은 `name_ko`, `name_latin`은 영문 이름이다. `name_aliases`는 `artist_aliases`를 ID 순으로 읽은 값이고, `related_artist_ids`는 자기 자신의 ID 하나다. 조회 단계에서 다른 아티스트 행과 묶지 않는다.
- 한국어 이름이 확인되지 않으면 `name_ko`는 비워 두며 번역·음역을 만들어 넣지 않는다. 한자 이름이 없는 아티스트에게 한자 이름을 만들지 않는다.
- 이름이 비슷하다는 이유로 아티스트·계정·방송·공연·알림 기록을 병합·삭제·이동하지 않는다. 같은 사람으로 확정된 경우에도 기존 ID·소유권·출처를 보존한다.
- 그룹과 멤버 관계는 `artist_group_members`, 소속은 `agencies`로 관리하며 이름으로 추론하지 않는다.

## 보존된 기존 경로

다음은 기존 DB 시절의 코드로, 현재 운영 경로에서 쓰지 않는다.

- `app/data/artist_identities.json`과 `app/core/artist_identity.py`: 검수한 이름 쌍과 별칭 목록, `name_key`(NFKC 정규화 후 공백·밑줄 제거, 대소문자 무시) 비교와 표시 이름 생성. 퍼지 매칭이나 기계 음역은 쓰지 않는다. 기존 수집 adapter와 기존 DB 등록 스크립트가 import한다.
- `scripts/normalize_artist_names.py`: 기존 DB의 `display_name`을 `원어 (Latin)` 형식으로 맞추던 도구다. 기존 DB 연결(`app/core/db.get_connection`)이 차단되어 지금 실행하면 오류로 끝난다.
- 구 API의 `GET /api/artists?grouped=true`(별칭으로 묶은 목록)는 마운트하지 않은 `artists` 라우터에 있다.

기존 데이터의 이름 출처로 남겨 둔 공식 자료는 다음과 같다. RIOT/V.W.P와 LIVE UNION 원어 이름은 기존 프로필 시드, RK Music 이름은 공식 [소속 목록](https://rkmusic.jp/info/30/)과 [KISAKI 프로필](https://rkmusic.jp/artist/312/), Girls Revolution Project 여섯 명의 이름과 영문 계정 식별자는 [KAMITSUBAKI 공식 팸플릿](https://kamitsubaki.jp/wp-content/uploads/2025/01/KAMICOLLE_Pamphlet.pdf)에 있다. 문서 정리 중에 다시 외부 확인한 것은 아니다.

## 테스트

```powershell
python -m pytest tests/test_artist_identity.py tests/test_read_api.py
```

프론트 검증은 [QA](../web/docs/qa.md)를 따른다.

## 변경 이력

- 2026-09-18: 기존 DB 기준으로 `artist_identities.json` 별칭 묶음과 `normalize_artist_names.py`(미리보기 기본, `--apply`는 `display_name`·`updated_at`만 변경), 별칭 묶음 목록 API를 정리했다.
- 2026-09-22 이후: 신규 DB와 `/api` 조회로 전환하면서 이름은 `name_native`·`name_ko`·`name_latin`·`artist_aliases`로 분리됐고, 조회는 아티스트 행을 묶지 않는다.
- 2026-11-21: 사용자 요청 표기를 신규 DB의 빈 `name_ko`에 반영했다: 오토노세 라코(ID 1041, otonose-raco), 스이우 시노(1044, suiu-shino), 니비이로 유루시(1045, nibiiro-yurushi), 아야무기(1046, yayamugi). 원어 이름·ID·소유권은 유지했다. 정확한 ID/slug를 확인한 dry-run 후 적용했으며 영수증 9924와 변경 이력 4건을 남겼다. 실제 프론트 프록시의 `/api/artists`에서 네 display_name을 대조했다. 사용자 지정 표기이며 별도 공식 한국어 표기 조사 결과는 아니다.
- 2026-11-23: 영어 문서를 한국어로 다시 쓰고 현재 코드와 대조했다.
