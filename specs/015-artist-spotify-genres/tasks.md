# 아티스트 Spotify 장르 작업 목록

- [x] T001 FR-001~005 요구·설계·완료 조건 연결.
- [x] T002 FR-002·003 provider 조회·정규화·재시도와 namespace 저장 스크립트.
- [x] T003 FR-004 조회 API 필드 추가.
- [x] T004 FR-005 아티스트 상세 장르 칩.
- [x] T005 SC-002 fixture·단위 테스트·빌드·실데이터 저장과 읽기 확인.
- [ ] T006 운영 배포 후 아티스트 상세 화면(PC·모바일) 검수.
- [ ] T007 장르가 비어 있는 아티스트의 보완 방법 결정(현재 표시 대상 75계정 중 8개만 값이 있음).

## 2026-11-24 검증 기록

- `pytest tests/test_spotify_artist_genres.py tests/test_spotify.py tests/test_youtube_channel_statistics.py tests/test_shared_youtube.py`: 37 passed, 3 skipped(로컬 PostgreSQL 바이너리 부재로 DB fixture skip).
- `npm run test`: 12개 파일·66개 테스트 통과, `npm run build`(TypeScript·Vite) 통과.
- 실데이터: `scripts/refresh_spotify_artist_genres.py --all-registered` 실행 결과 `{"requested": 75, "updated": 75, "with_genres": 8, "unavailable": 0}`. 첫 실행은 Spotify 일시 오류(`provider_error`)로 저장 전에 중단되어 재시도 처리를 추가했다.
- 읽기 전용 조회 서비스: 아티스트 128명 중 8명에 장르 표시. 값은 `j-pop` 7, `vocaloid` 2, `space music` 1. 카탈로그 비표시 아티스트(요루시카·LiSA 등) 계정 11개는 대상에서 제외되며 이들 중심으로 `anime`·`j-rock` 값이 있었다.
- 수집 설정·다른 provider_state·외부 전송은 변경하지 않았다. 운영 배포는 하지 않았다.
