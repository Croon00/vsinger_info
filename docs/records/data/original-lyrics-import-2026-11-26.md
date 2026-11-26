# 오리지널 곡 가사 일괄 등록 (2026-11-26)

## 내용

- 대상: `db-migration/reports/original-lyrics-2026-11-25/candidates.json` 608건 (YouTube 설명란·댓글 자동 추출)
- 사용자 요청으로 **검토 전 일괄 승인**: 모든 항목을 `approved: true`로 바꾸고, 비어 있던 `note`에 "2026-11-26 사용자 요청으로 검토 전 일괄 등록"을 기록했다. 승인 전 파일은 세션 임시 폴더에 백업했다.
- 실행: `scripts/import_original_lyrics.py candidates.json` 미리 보기 후 `--apply`

## 결과

- `source_documents` 608행, `recording_lyrics` 662행(같은 영상으로 묶인 녹음 포함)을 추가했다. 기존 가사·보관 녹음으로 건너뛴 항목은 0건이다.
- 등록 즉시 `GET /api/recordings/{id}/lyrics`와 아티스트 오리지널 탭 `가사` 버튼으로 공개된다.
- 확인: 활성 `recording_lyrics` 662행 / 출처 문서 608개. MEDA 오리지널 14곡 중 8곡에 `lyrics_recording_id`가 있다.

## 남은 작업

- 사용자가 화면에서 읽어 보며 잘못 추출된 가사(크레딧·해시태그 혼입, 잘림)를 확인한다. 수정·숨김은 `recording_lyrics.archived_at` 또는 본문 수정으로 처리하며 아직 도구는 없다.
