# 오리지널 곡 가사 등록

최종 확인 2026-11-25. 요구사항과 검증 기록은 [016-original-lyrics-review](../specs/016-original-lyrics-review/spec.md)에 있다.

가사는 사람이 검토해 승인한 항목만 `recording_lyrics`에 저장한다. **저장 즉시 `/api/recordings/{id}/lyrics`와 발매곡 목록의 `has_lyrics`로 공개된다.** 설명란·댓글 가사도 저작권은 원저작자에게 있고, YouTube API 데이터 보관 정책이 적용될 수 있으므로 공개 여부는 항목별로 판단한다. 팬 댓글은 정확도를 보장하지 않는다.

## 1. 후보·직접 입력 파일 만들기 (DB 변경 없음)

```powershell
.venv\Scripts\python.exe scripts/export_original_lyrics.py
.venv\Scripts\python.exe scripts/export_original_lyrics.py --skip-comments   # 설명란만
.venv\Scripts\python.exe scripts/export_original_lyrics.py --limit 20        # 시험 실행
```

출력(Git 제외): `db-migration/reports/original-lyrics-<날짜>/`

| 파일 | 내용 |
| --- | --- |
| `candidates.json` | 공식 영상 설명란 또는 가사라고 알린 댓글에서 찾은 후보. `source_text`에 원문 전체 |
| `manual-with-video.json` | 공식 영상은 있지만 가사를 찾지 못한 곡 |
| `manual-no-video.json` | 공식 영상이 연결되지 않은 곡 |
| `excluded-covers.json` | 오리지널에서 제외한 발매 커버 음원(참고용, 가져오기 대상 아님). 기준은 [곡 탐색](song-exploration.md#오리지널) |

## 2. 검토와 작성

항목의 주요 필드: `key`, `recording_ids`(같은 영상을 공유하는 녹음 전체), `title`, `artist`, `youtube_url`, `status`, `source_kind`(`video_description`·`youtube_comment`·`official_page`·`announcement`·`manual_note`), `source_url`, `source_author_is_channel_owner`, `original_lyrics`, `translation_ko`, `pronunciation_ko`, `approved`, `note`.

- 후보: `original_lyrics`의 앞뒤를 원문과 대조해 고치고 공개할 항목만 `approved: true`.
- 직접 입력: `original_lyrics`를 채우고, 근거가 있으면 `source_kind`·`source_url`을 바꾼 뒤 `approved: true`.
- `translation_ko`·`pronunciation_ko`는 선택이며 빈 값은 NULL로 저장한다.

## 3. 등록

```powershell
.venv\Scripts\python.exe scripts/import_original_lyrics.py <파일...>          # 미리보기
.venv\Scripts\python.exe scripts/import_original_lyrics.py <파일...> --apply  # 저장
```

승인 항목만 한 트랜잭션으로 저장한다. 같은 키를 두 번 승인하면 중단한다. 보관된 녹음, 이미 가사가 있는 녹음은 건너뛰며 기존 가사를 덮어쓰지 않는다. 출처는 `source_documents`에 내용 해시로 한 번만 남는다.
