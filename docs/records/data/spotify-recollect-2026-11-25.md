# Spotify 재수집과 미연결 계정 연결 (2026-11-25)

사용자 요청: 등록된 아티스트 전부 수집. 운영 DB에 작업을 넣고 배포된 worker가 처리했다. 수치는 기록 시점 값이다.

## 1. 연결 계정 재수집 (`--run refresh-2026-11-25`)

- 대상: 표시 중 아티스트의 owner Spotify 계정 75개. 이전 수집은 2026-09-27~10-10이 마지막이었다(정기 실행 없음).
- 2026-09-28 quota 소진 기록에 따라 20·20·20·15개 계정으로 나눠 `scripts/start_spotify_collection.py --limit N --apply`로 시작했다.
- 결과: 작업 382개 모두 성공(02:10–04:31 UTC), 오류·429 0. 새 앨범 66개, 새 녹음 95개, ISRC 기준 기존 녹음에 Spotify ID 187개 추가. 10월 이후 발매 30개(예: 시엘 `晴途`, 우스와 스우 `Synchrony`, 코코 `Facets`, 아즈키 `推したら引けない恋でした`), 이전 수집에서 빠진 2020–2025 발매 33개.

## 2. 미연결 54명 계정 조사와 연결

- `scripts/discover_spotify_accounts.py`(정확한 이름, 읽기 전용) → 유일 일치 8, 검색 미완 30, 미발견 15, 복수 1.
- `scripts/spotify_account_candidates.py research`(Wikidata·제목 겹침, 읽기 전용). Wikidata가 연락처 없는 User-Agent를 403으로 거부해 저장소 URL을 넣었다. 요청 278회, 후보 있음 35명.
- 사용자 결정(2026-11-25): 근거 확실 12명, 고유 이름 7명, Spotify 프로필 화면으로 대조한 5명(Figaro, 白玖ウタノ, nayuta, CYBILL, MaiR) 연결. HONK THE HORN·NUROJUNK는 그룹 계정을 owner로, 멤버(MOCO·BAMBI / SAKUYA·KAGURA)는 `member`로 연결. 그룹 계정은 Spotify 발매작과 그룹 공식 YouTube MV 제목(5/5, 3/3) 일치를 확인했다. INARI·揺蕩 제외, くろくも·NoiR·shin·宮島ルシェル 미연결, 후보 없음 19명.
- 결정 파일: [spotify-account-decisions-2.json](../../../migrations/catalog/spotify-account-decisions-2.json). `apply --apply` 결과 `catalog_imports` #10888, 계정 26개 생성, 연결 30건.
- 코드 보완: 결정 파일 경로 `--decisions`, 같은 실행에서 그룹·멤버가 공유하는 계정을 한 번만 생성, 수집 대상에 숨김 상태의 승인된 오리지널 그룹(`original_song_groups`) 포함.

## 3. 새 연결 계정 수집 (`--run linked-2026-11-25`)

- 대상 27개 계정: 새 연결 26개 + VESPERBELL. VESPERBELL은 그룹 계정이 등록돼 있었지만 그룹이 숨김 상태라 수집 대상에서 빠져 있었다.
- 결과: 수집 켬 27개, 작업 144개 모두 성공(05:19–06:01 UTC), 오류·429 0.
- 아티스트별 녹음: nayuta 363(앨범 187, 동인·컴필레이션 참여작 다수), 마이사키 베리 56, VESPERBELL 52, 호시노 메아(MaiR) 45, 니비이로 유루시 29 등.
- 오리지널 목록: 2,222 → 2,852항목(발매 커버 제외 규칙 적용 후).

## 4. KMNZ 그룹 계정과 멤버 화면

- KMNZ 그룹(숨김, 승인된 오리지널 그룹)에 `4uWpa0r7BZUXJ1ip2LJysz`를 owner로 연결했다(`catalog_imports` #11034, [decisions-3](../../../migrations/catalog/spotify-account-decisions-3.json)). 근거: Spotify 발매작과 KMNZ 채널 공식 영상 제목 일치. 수집 작업 6개 성공.
- LITA·TINA·NERO는 본인 계정이 있어 그룹 계정을 `member`로 추가하지 않았다(아티스트당 Spotify 연결 1개 규칙). 그룹 발매는 승인된 오리지널 그룹 규칙으로 멤버 화면에 표시한다.
- 같은 날 `/api/artists/{id}/albums`가 승인된 그룹 멤버에게 그룹 발매도 반환하도록 바꿨다([조회 API](../../read-api.md)). 결과: KMNZ 디스코그래피 30, LITA 33, TINA 38, NERO 31, 오리지널 각 162. BAMBI·MOCO 5, ヨミ·カスカ 15, SAKUYA 3.

## 후속

- 가사 검토 파일 재생성: 후보 608, 직접 입력 2,244(영상 있음 138, 영상 없음 2,106), 제외 커버 352. [016](../../../specs/016-original-lyrics-review/tasks.md)
- nayuta처럼 참여작이 많은 계정의 컴필레이션 수록곡이 오리지널 목록에 어떻게 보이는지 화면 검수가 필요하다.
- Spotify 정기 재수집은 여전히 없다.
