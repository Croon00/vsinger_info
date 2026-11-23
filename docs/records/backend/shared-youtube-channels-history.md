# 공유 YouTube 채널 변경 이력

현재 기준은 [공유 YouTube 채널](../../shared-youtube-channels.md)을 따른다. 아래는 2026-11-01 작업 당시의 반영·검증 기록이며 수치는 기록 시점 값이다. 2026-11-23 현재 문서에서 분리했다.

## 2026-11-01 공유 채널 통계·커버 수집

실제 API로 두 채널 통계를 갱신해 VESPERBELL 367,000명, KMNZ 314,000명을 확인하고 각 멤버의 조회 값이 동일한지 검증했다. 기존 멤버/그룹 원본과 그룹 소유 관계 두 건은 유지했다. 두 채널의 과거 업로드 27페이지를 완료하고 커버 220개를 추가했으며 조회수 220개와 짧은 영상 형식 119개도 확인했다.

이번 추가 수집은 공유 채널 두 개만 선택하고 요청 간격 2초·해당 실행의 24시간 예산 2,000회로 실행했다. 도구의 기본 예산 1,500회는 변경하지 않았다.

규칙·회귀 Python 테스트 21개 통과, 로컬 PostgreSQL이 필요한 6개는 건너뛰었다. PC·모바일 기존 아티스트 정렬·곡 탐색·가창자 선택 브라우저 테스트 6개와 프론트 단위 테스트 56개 및 빌드를 검증했다. fixture 테스트와 실제 DB·provider 확인은 구분한다.

## 2026-11-01 별도 음악 채널 출처 누락 복구

초기 검증은 원래 등록된 채널 ID로 저장된 영상만 대상으로 했으므로 TINA·NERO의 일반 커버가 없다는 결론은 잘못되었다. 전체 업로드 목록을 다시 대조해, 목록에는 포함되어도 `videos.list.snippet.channelId`가 별도 음악 채널인 영상이 기존 동일 채널 필터에서 누락됨을 확인했다. 예: NERO `Revival`/`Stormy`, カスカ `ホログラム`, ヨミ `狭心症`.

복구 후 두 채널 전체 27페이지의 커버 후보 KMNZ 294개·VESPERBELL 287개 모두 저장됨을 실데이터로 대조했다(Shorts 후보 포함). 누락 267개를 추가하고 조회수 267개 및 짧은 영상 형식 34개를 갱신했다. 과거 라이브로 등록되었지만 출처 계정이 비어 있던 완료 커버 프리미어 1개는 정확한 API 채널 ID로 빈 출처를 연결하고 커버 행을 추가했다. 기존 라이브·가창 기록과 이미 지정된 출처는 보존했다. 같은 목록 재저장 시 추가 0개를 확인했다. `Stormy`는 NERO·ヨミ 모두에, `Revival`은 NERO에만, `ホログラム`은 カスカ에만, 멤버 표기가 없는 `Rambling Beast`는 KMNZ 세 멤버 모두에 노출됨을 확인했다. 전역 곡 탐색과 로컬 HTTP 200 응답도 확인했다.

당시 추가 출처 계정 ID는 323–329였다. 회귀 테스트 36개 통과, 폐기 가능한 로컬 PostgreSQL이 필요한 7개는 미설치로 건너뛰었다. 이 fixture 검증과 앞의 실제 DB·provider 대조는 별도다.

## 2026-11-01 전역 커버 목록 보완

곡 탐색의 커버 목록에 두 승인 그룹 owner를 표시 명의로 포함했다. 관련 Python 테스트 16개 통과, 로컬 PostgreSQL이 필요한 5개는 건너뛰었다. 실제 신규 DB에서 그룹명 검색·RK Music 필터·중복 없는 영상 키를 확인하고 개인 멤버별 건수는 유지됨을 확인했다.

## 2026-11-01 오리지널 발매곡 누락 보완

커버 전체 수집 완료는 오리지널 발매곡 수집 완료를 뜻하지 않는다. 확인 당시 그룹 명의 recording은 KMNZ·VESPERBELL 모두 0개였고, 오리지널 탐색의 공개 아티스트 조건도 숨겨진 그룹 명의를 제외했다. Spotify 연결은 토큰 발급 단계에서 실패했다.

두 본채널의 전체 업로드 27페이지(1,322개)를 공식 API로 대조하고, 검토한 오리지널 MV 50개를 `migrations/catalog/shared-original-videos-2026-11-01.json`에 원본 제목·채널 ID·등록일·설명과 함께 보존했다. 그룹 MV는 그룹 명의로, 명시적인 ヨミ·カスカ 솔로와 HACHI 협업은 확인한 실제 명의로 등록했다. MV 없는 앨범 수록곡과 이번 검토에서 제외한 외부 협업은 완전 수집으로 간주하지 않는다.

`UCKaDMw10CmbE22XJhaunoiQ`는 `channels.list`의 VESPERBELL 채널과 본채널 업로드 목록에 포함된 「一閃」「Bell Ringer」의 실제 publisher를 함께 확인한 추가 음악 출처다. 본채널 구독자 통계 우선순위는 유지했다.

```powershell
.venv\Scripts\python.exe scripts/import_reviewed_original_videos.py migrations/catalog/shared-original-videos-2026-11-01.json
# 검토된 manifest 적용
.venv\Scripts\python.exe scripts/import_reviewed_original_videos.py migrations/catalog/shared-original-videos-2026-11-01.json --apply
```

실제 신규 DB 반영: 공식 MV 50개·recording 50개를 감사 기록 7501로 등록하고 각 영상의 조회수와 등록일을 연결했다. 기존 HACHI 「Admit (VESPERBELL ヨミ ＆ HACHI）」 발매는 실제 협업 명의와 길이 차이 1.392초를 대조해 같은 공식 MV에 연결했다(감사 기록 7502). 기존 발매 행·크레딧은 보존하고 탐색의 영상 ID 중복 제거를 적용한다. 반복 실행은 `already_applied`로 추가 0개다.

검증: fixture 테스트 16개 통과, 로컬 PostgreSQL이 없는 DB fixture 10개는 건너뛰었다. 별도 실제 신규 DB 읽기 검증에서 KMNZ 멤버별 공식 MV 32개, ヨミ 17개, カスカ 16개와 중복 없는 영상 ID를 확인했다. VESPERBELL 검색 18개 모두 조회수·등록일이 있으며, 로컬 API는 ヨミ 선택 시 HTTP 200·17개를 반환했다. KMNZ 멤버의 기존 MV 미연결 발매 행은 보존했다. 이 보완은 검토한 공식 MV 반영이며, Spotify 토큰 발급 문제와 MV 없는 수록곡 보완은 남아 있다.

같은 날 오리지널 곡 탐색은 VESPERBELL·KMNZ·HONK THE HORN·NUROJUNK 단위로 멤버 발매곡의 표시 명의와 아티스트 선택지를 묶었다. 실제 가창 명의·채널 소유권은 유지하며 커버/우타와꾸의 개인 분리는 기존대로다. 상세 기준과 검증은 [곡 탐색](../../song-exploration.md)에 있다.
