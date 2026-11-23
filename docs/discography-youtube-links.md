# 디스코그래피 YouTube 연결

최종 확인 2026-11-23. 2026-10-11 실데이터 적용 결과와 검증은 [적용 기록](records/data/discography-youtube-links-2026-10-11.md)에 있다.

발매곡(recording)별로 검증된 YouTube 링크를 연결한다. 기존 `recordings.official_video_id`와 `videos`를 사용하며 schema 변경은 없다.

## 조회와 화면

- `/api/albums/{id}`의 트랙은 `youtube_url`을 반환한다. 보관/비공개/삭제/공개 여부 미확인 영상은 반환하지 않으며(null) 조회 API는 검색·수집을 실행하지 않는다.
- 웹은 링크가 있는 곡만 `YouTube로 보기` 버튼을 표시한다. shadcn Button의 youtube variant(검은 배경·흰 글씨·흰 테두리·알약 모양)를 쓰고, hover와 focus-visible은 빨간색으로 채우며 reduced-motion에서는 즉시 전환한다. 새 탭 링크는 `noopener noreferrer`를 사용한다.
- compact hero 미리보기는 기존 구성을 유지하고 앨범 상세에서 곡별 버튼을 제공한다.

## 조사·연결 도구

```powershell
python scripts/link_discography_youtube.py --output outputs/discography-youtube-<배치명>
python scripts/link_discography_youtube.py --apply --output outputs/discography-youtube-<배치명>
```

| 옵션 | 동작 |
| --- | --- |
| (기본) | 통합 DB 읽기, YouTube API 읽기, 로컬 보고서 작성만 수행 |
| `--apply` | 검증된 링크를 감사 이력과 함께 저장 |
| `--max-pages N` | 채널당 업로드 목록 페이지 상한. 기본 60, 허용 1~100 |
| `--direct-connect` | 로컬 proxy 문제가 있을 때만 사용 |
| `--output DIR` | 필수. 같은 디렉터리는 같은 조사의 재개용 캐시이며 새 조사는 새 디렉터리를 쓴다 |

### 판정 기준

- 등록된 가창자의 owner 채널 업로드 목록([`playlistItems.list`](https://developers.google.com/youtube/v3/docs/playlistItems/list), 페이지당 최대 50개)을 읽고, 제목 후보만 videos API로 곡명·버전·공개 상태·재생 길이를 확인한다.
- 제목은 완전한 필드/인용 제목 기준으로 비교하며 짧은 부분 문자열만으로 연결하지 않는다. 피처링 표기를 분리하면 영상 제목에 같은 피처링 명의가 있어야 하며 뒤에 붙은 버전 표기는 유지한다.
- Instrumental, acoustic/piano, remix, short, live 버전 차이는 보류하고 방송·리액션·티저·XFD는 제외한다.
- 종료된 공식 MV/Original 최초 공개는 완료된 영상으로 인정하지만 진행 중/예약 영상과 일반 노래 방송은 제외한다.
- 여러 후보 중 유일한 full MV를 우선하고, 같은 우선순위 후보가 여러 개면 보류한다.
- 자동 배포 음원은 공식 owner 채널에 있는 경우만 인정한다. 별도 Topic/레이블 채널이나 명의 미등록 가창자는 이름만으로 소유권을 추정하지 않는다.

### 적용

- `--apply`는 catalog identity와 기존 recording version 및 owner 관계를 다시 확인한다.
- 기존 링크를 덮어쓰지 않으며 catalog_imports/catalog_changes에 영상 생성/공개 상태 갱신/녹음 연결의 전후 데이터를 보존한다. 자동 판정 근거는 채널 ID와 영상 ID로 기록한다. 중복 operation은 `already_applied`를 반환한다.
- 알림·LLM·Calendar·가사·새 방송 세트리스트 추출은 실행하지 않는다.

### 보고서

- `unresolved.csv`: recording_id, 실제 가창 명의, 곡명, 수록 발매, 보류 사유, 빈 youtube_url 열
- `unresolved.md`: 가창 명의별 목록

공식 owner 채널과 검증 조건 기준으로 자동 연결을 확정하지 못한 목록이며, 플랫폼 전체에서 영상이 없다는 증거가 아니다. 사용자가 URL을 주면 녹음 ID와 버전을 기준으로 후속 검토한다.
