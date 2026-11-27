# 곡 월드컵 공개 랭킹 운영 적용

2026-11-27 운영 DB의 적용 버전이 `001`~`007`이며 유일한 대기 버전이 `008`임을 확인했다. 운영 사이트의 월드컵 후보 집계 API가 HTTP 200, 랭킹 API가 월드컵 테이블 준비 전을 나타내는 HTTP 503을 반환했다.

- `scripts/migrate_catalog.py --apply`로 `008`을 적용했다. 별도 읽기 전용 트랜잭션에서 `--verify`와 같은 검증 함수로 스키마를 재확인했다.
- 운영 `GET /api/worldcup/stats`는 오리지널·커버 모두 HTTP 200, 완료 판 0건, 랭킹 곡 0곡을 반환했다. DB에도 완료 판과 대결 기록이 0건이었다. 기존 라이브 상세 API도 HTTP 200을 반환했다.
- 운영 `POST /api/worldcup/results`에 빈 본문 객체를 보내 백엔드의 필수 필드 검증과 HTTP 422 응답을 확인했다. 첫 실제 완료 판의 저장과 공개 랭킹 반영은 이후 확인할 항목이다.
- 로컬 fixture 검증에서 `pytest tests/test_worldcup.py -q` 15개가 통과했다.
