# 공유 YouTube 채널

최종 확인 2026-11-23 · 실데이터 반영·검증 경위는 [변경 이력](records/backend/shared-youtube-channels-history.md)에 있다.

사용자가 지정한 두 공식 그룹 채널에만 다음 표시 규칙을 적용한다. 이름만으로 계정을 병합하지 않으며 원본 영상·채널 소유권·멤버의 다른 계정은 변경하지 않는다.

| 그룹·본채널 | 공유 멤버 |
| --- | --- |
| VESPERBELL · `UCPd0Z22gF43dUidPYEQO5-w` | ヨミ / YOMI, カスカ / KASUKA |
| KMNZ · `UCwuS0uY-Z2Gr_5OV2oFybFA` | LITA, TINA, NERO |

[`app/repositories/shared_youtube.py`](../app/repositories/shared_youtube.py)의 명시적 규칙(`RULES`), 기존 `artist_group_members` 관계, 해당 그룹이 실제 소유한 채널 ID를 함께 확인한다. 보관된 아티스트·계정 또는 종료된 멤버 관계는 공유 대상으로 사용하지 않는다. 그룹 자체가 탐색 목록에서 숨겨져 있어도 공개된 위 멤버의 공유 채널로는 사용할 수 있다. 다른 그룹에 자동 확장하지 않는다.

## HONK THE HORN·NUROJUNK 멤버별 표시

2026-11-22 추가 승인으로 두 그룹(HONK THE HORN: MOCO·BAMBI, NUROJUNK: SAKUYA·KAGURA)을 멤버별로 나눈다. 위 VESPERBELL·KMNZ 규칙과 달리 공식 재생목록·검토 근거로 진행자를 연결한다. 요구·설계·작업은 [013](../specs/013-shared-member-catalog/spec.md), 반영 수치와 한계는 [반영 기록](shared-members-2026-11-22.md)에 있다.

- 커버(HONK): 제목에 MOCO 또는 BAMBI 한 명이 있으면 그 멤버에게만, 둘 다 있거나 둘 다 없으면 두 멤버에게 표시한다. 부분 일치는 쓰지 않으며 같은 채널의 명시적 이름이 기본·검토 배정보다 우선한다. 다른 협업자 이름만 있어도 미표기 기본값을 적용한다.
- 커버(NUROJUNK): 미표기 영상은 공식 근거·개별 검토를 요구한다.
- 공동 영상은 공식 공동 재생목록과 설명 MC/Vocal을 확인한 경우에만 여러 멤버에게 표시하며, 실제 publisher·영상 ID는 유지한다. 이름 없는 연습 음원·Shorts는 개인 본편 목록에 배정하지 않는다(Shorts는 계속 제외).
- 라이브: HONK는 공식 MOCO/BAMBI STREAMS 재생목록으로 나눈다. NUROJUNK는 같은 목록이 없어 공식 썸네일·제목을 개별 검토한 방송만 사용하고 근거는 [검토 manifest](../migrations/catalog/nurojunk-stream-members-2026-11-22.json)에 보존한다. 썸네일 자동 얼굴 인식은 하지 않으며, 명시적 진행자 제목 외에는 검토 대상이다. 근거가 부족한 방송은 그룹 상태로 둔다. 합동 방송은 두 멤버를 연결한다.
- 네 멤버의 개인 라이브·통계는 지정 그룹 공식 채널의 비커버 방송으로 제한하고 외부 원곡 MV·커버 프리미어는 제외한다. 커버는 솔로 이름과 검토한 듀엣·공동 영상 명의를 사용한다. 그룹 owner·기존 가창·원문은 보존하며 다른 가창자가 지정된 곡은 덮어쓰지 않는다.
- 일일 poll·collect가 재대조한다(`app/repositories/shared_member_youtube.py`). 명시적 보완은 `scripts/repair_shared_youtube_members.py --input PATH --group honk-the-horn|nurojunk`이며 `--apply`가 실제 반영이다.

## 추가 음악 출처 채널

그룹 본채널 업로드 목록에 포함되지만 `videos.list.snippet.channelId`가 별도 음악 채널인 영상이 있다. `shared_youtube.COVER_SOURCE_CHANNELS`에는 공식 업로드 목록 소속과 실제 영상 채널 ID를 함께 검증한 출처만 명시한다(KMNZ 본채널 외 5개, VESPERBELL 본채널 외 3개).

- 각 출처는 그룹 owner의 별도 external account로 등록하고, 영상은 원래 영상의 채널 ID에 해당하는 계정으로 저장한다. 그룹 본채널 ID로 덮어쓰지 않는다.
- 원래 채널의 업로드 목록에서 이 영상들을 만나면 승인 출처로 나누어 저장한다. 승인되지 않은 외부 채널 영상은 제외한다. 이름만으로 소유 관계를 추론하지 않는다.
- 출처 계정도 수집 활성 상태라 이후 수집 대상이다. 공유 멤버 배정·전역 탐색에 포함되지만 구독자 통계는 `is_statistics_source`인 본채널에서만 가져온다.

## 구독자 수와 링크

멤버 프로필과 아티스트 목록의 구독자 수·채널 생성일은 공유 본채널 통계를 사용한다. 개인 구독자 수로 합산하거나 복제 저장하지 않는다. 조회 API는 nullable `youtube_statistics_source`로 그룹 이름을 반환하고, 화면은 구독자 툴팁에 `KMNZ 채널 구독자 314,000명`처럼 출처를 표시한다. 멤버의 YouTube 링크도 그룹 공식 채널을 안내하며, 멤버가 채널 owner인 것처럼 새 관계를 만들지 않는다.

## 커버의 멤버별 표시

- `KMNZ TINA`, `VESPERBELL ヨミ`, 명시적 멤버 이름 괄호·covered by 표기 등 가창 명의 문맥을 확인한다. 원곡 가수 `Tina Turner`가 제목에 있다는 이유만으로 TINA 솔로로 취급하지 않는다.
- 멤버 한 명을 명시하면 그 멤버에게만, 두 명 이상이면 명시한 멤버들에게만 표시한다.
- 멤버가 명시되지 않았으면 사용자 지시에 따라 업로드 그룹의 대상 멤버 전원에게 표시한다. 사용자 지정 표시 정책이며 개별 가창 검증이 완료됐다는 뜻이 아니다.
- 두 공유 채널 사이의 명시적 협업(예: `KMNZ LITA & VESPERBELL ヨミ`)은 명시한 두 멤버에게 표시한다. 다른 채널로 이 추론을 확장하지 않는다.
- `KMNZ LIZ`처럼 대상 밖 명의가 명시된 것을 현재 세 명의 합창으로 바꾸지 않는다. 기존 그룹 명의·원본은 보존한다.
- 제목의 커버 근거, 공개 상태, Shorts 제외 등 기존 조회 조건을 먼저 적용한다. 물리적인 영상 복제나 `cover_artists` 명의 덮어쓰기는 하지 않는다.

곡 탐색의 커버 목록은 두 승인 그룹 owner도 표시 명의에 포함한다. 그룹이 아티스트 탐색에서 숨겨져 있어도 공유 채널 영상은 전체 커버 목록에 남으며 `VESPERBELL · ヨミ`, `KMNZ · LITA`처럼 그룹명과 멤버를 함께 표시한다. 같은 영상은 한 번만 표시하고 멤버 이름 검색에도 같은 규칙을 적용한다. 대상 밖 명의가 붙은 영상은 전역 목록에 남지만 현재 멤버에게 배분하지 않는다. 일반 숨김 아티스트에는 이 예외를 적용하지 않으며 소속사·Shorts·커버 판별 조건도 유지한다.

## 오리지널 발매곡

오리지널 곡 탐색은 승인된 두 그룹 명의도 표시한다. 현재 멤버를 선택하거나 이름으로 검색하면 소속 그룹의 발매곡도 조회하지만, 표시 명의와 저장된 가창 크레딧은 그룹 그대로다. 과거 발매에 현재 멤버가 모두 참여했다는 의미는 아니다. 그룹 단위 표시 기준은 [곡 탐색](song-exploration.md)을 따른다.

커버 전체 수집이 오리지널 발매곡 수집 완료를 뜻하지는 않는다. 오리지널 MV는 검토한 manifest를 `scripts/import_reviewed_original_videos.py`(기본 dry-run, `--apply`로 반영, 같은 operation 재적용 없음)로만 등록한다. 커버·Shorts·라이브 발췌를 일괄 오리지널로 분류하지 않으며, 그룹 MV는 그룹 명의로, 명시적인 솔로·협업은 확인한 실제 명의로 등록한다. 일반 YouTube 수집은 오리지널을 자동 분류·등록하지 않는다. MV 없는 앨범 수록곡과 Spotify 연결은 미완료다.

## 수집과 갱신

현재 신규 DB에서 그룹 본채널 계정 ID는 KMNZ=5, VESPERBELL=12이고, 추가 출처 계정은 323–329 등 별도 ID다. 다른 DB에서는 등록 계정 ID를 먼저 확인한다. 조회수·Shorts 갱신 시 본채널과 추가 출처 계정을 함께 선택한다.

```powershell
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py --account-id 5 --account-id 12
.venv\Scripts\python.exe scripts/backfill_catalog_youtube_covers.py --account-id 5 --account-id 12 --until-complete
.venv\Scripts\python.exe scripts/refresh_youtube_video_statistics.py --account-id 5 --account-id 12
.venv\Scripts\python.exe scripts/classify_youtube_cover_formats.py --account-id 5 --account-id 12
```

표시 중 멤버가 있는 두 승인 그룹은 그룹의 `show_in_catalog`가 false여도 통계 갱신·수집 대상이다. 계정의 수집 활성 여부는 유지하며 다른 숨김 그룹을 새 대상으로 삼지 않는다. 과거 수집은 기존 체크포인트·최근 24시간 요청 카운터를 사용하고 도구의 기본 예산(1,500회)을 따른다. 조회 API는 수집·갱신을 시작하지 않는다.
