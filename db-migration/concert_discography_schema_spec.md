> 이전 참고안입니다. 사용자 결정이 반영된 현재 기준은 [새 DB 전체 명세](새_DB_테이블_필드_명세.md)와 [DB 구조 계획](db-renewal-plan.md)입니다. 아래 원본의 크레딧·고정 게스트·역할 구분 등은 현재 사양으로 적용하지 않습니다.

﻿# 공연 및 음원·커버곡 DB 스키마 사양서 (Concert & Discography Schema Spec)

기준일: 2026-09-19  
용도: schedule_music DB 리뉴얼 - 공연 일정, 출연진, 앨범/음원 트랙, 가사 크레딧, 유튜브 커버 영상 정규화 규격

---

## 1. 전체 구조 및 연결 관계 (Overview)

```text
[공연 영역]
concerts (공연 본체) ───(1:N)───▶ concert_artists (공연 출연진 명단 - 다중 게스트/페스티벌 완벽 지원)

[음원 & 가사 영역]
albums (발매 앨범) ───(1:N)───▶ tracks (수록곡) ───(1:1)───▶ track_lyrics (가사, 한국어번역, 크레딧)
                                   │
                                   ▼
                             songs (앞서 정의한 곡 마스터와 연결)

[커버곡 영역]
youtube_covers (커버 MV 본체) ───(1:N)───▶ cover_artists (커버 참여자 명단 - 단체 합창 완벽 지원)
       │
       ▼
 songs (원곡 마스터와 연결)
```

---

## 2. 테이블 상세 사양

### ① 공연 테이블: `concerts` (공연 본체)

공연의 시간, 장소, 티켓 정보 메타데이터를 담는 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 공연 고유 번호 | `1` |
| **`title`** | TEXT | NOT NULL | 공연 공식 타이틀 | `'KAMITSUBAKI FES '24'` |
| **`event_format`** | TEXT | NOT NULL | 공연 형태 (`'onsite'`, `'online'`, `'hybrid'`) | `'hybrid'` |
| **`starts_at`** | TIMESTAMPTZ | NOT NULL | **공연 시작 일시 (타임존 포함)** | `2024-01-14 17:00:00+09` |
| **`city`** | TEXT | NULL 허용 | 개최 도시 (온라인 전용이면 `NULL`) | `'도쿄'`, `'요코하마'` |
| **`venue`** | TEXT | NULL 허용 | 공연장/장소명 (온라인 전용이면 `NULL`) | `'파시피코 요코하마 국립대홀'` |
| **`ticket_url`** | TEXT | NULL 허용 | 공식 티켓 예매 링크 URL (없으면 `NULL`) | `'https://l-tike.com/...'` |
| **`ticket_opens_at`** | TIMESTAMPTZ | NULL 허용 | 티켓 예매 시작 일시 (모르면 `NULL`) | `2023-11-01 12:00:00+09` |
| **`ticket_closes_at`**| TIMESTAMPTZ | NULL 허용 | 티켓 예매 마감 일시 (모르면 `NULL`) | `2024-01-10 23:59:00+09` |
| **`price_text`** | TEXT | NULL 허용 | 티켓 가격 안내 문구 (없으면 `NULL`) | `'일반 지정석 9,800엔 (세금포함)'` |
| **`source_url`** | TEXT | NULL 허용 | 공지 출처 링크 URL (없으면 `NULL`) | `'https://x.com/...'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 02:20:00+09` |

---

### ② 공연 출연진 테이블: `concert_artists` (출연자 명단)

페스티벌이나 게스트 출연을 1명부터 20명까지 자유롭게 담는 연결 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 | 설명 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`concert_id`** | INTEGER | NOT NULL, FK(`concerts.id` ON DELETE CASCADE) | 어느 공연인가? | `1` (KAMITSUBAKI FES) |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 출연 아티스트 번호 | `1` (카프), `2` (리메)... |
| **`is_headliner`** | BOOLEAN | NOT NULL, DEFAULT TRUE | 메인 주최자 여부 | 단독 공연이면 주최자만 `TRUE`, 페스티벌은 전원 `TRUE` |

* **복합 기본키(PK)**: `(concert_id, artist_id)`

---

### ③ 발매 앨범 테이블: `albums` (Spotify 앨범)

아티스트가 발매한 정식 음원 앨범(싱글, EP, 정규 등) 목록입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 앨범 고유 번호 | `101` |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id`) | 발매 아티스트 번호 | `1` (카프) |
| **`title_native`** | TEXT | NOT NULL | 원어 앨범 제목 | `'狂想'` |
| **`title_ko`** | TEXT | NULL 허용 | 한국어 표기 (없으면 `NULL`) | `'광상'` |
| **`album_type`** | TEXT | NOT NULL | 앨범 종류 (`'single'`, `'ep'`, `'album'`, `'compilation'`) | `'album'` |
| **`release_date`** | DATE | NOT NULL | 공식 발매일 (`YYYY-MM-DD`) | `'2023-03-08'` |
| **`cover_image_url`**| TEXT | NULL 허용 | 앨범 커버 이미지 URL (없으면 `NULL`) | `'https://i.scdn.co/image/...'` |
| **`spotify_album_id`**| TEXT | NULL 허용 | 스포티파이 앨범 고유 ID (없으면 `NULL`) | `'2oZ...'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 02:20:00+09` |

---

### ④ 수록곡 트랙 테이블: `tracks` (오리지널 음원 트랙)

앨범 안에 들어있는 개별 수록곡들입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 트랙 고유 번호 | `2001` |
| **`album_id`** | INTEGER | NOT NULL, FK(`albums.id` ON DELETE CASCADE) | 어느 앨범 수록곡인가? | `101` (광상) |
| **`track_number`** | INTEGER | NOT NULL | 앨범 내 트랙 순번 | `1` |
| **`title_native`** | TEXT | NOT NULL | 원어 트랙 곡명 | `'過去を喰らう'` |
| **`title_ko`** | TEXT | NULL 허용 | 한국어 번역 곡명 (없으면 `NULL`) | `'과거를 먹는 자'` |
| **`duration_ms`** | INTEGER | NULL 허용 | 곡 재생 길이 (밀리초, 모르면 `NULL`) | `215000` (3분 35초) |
| **`spotify_track_id`**| TEXT | NULL 허용 | 스포티파이 트랙 ID (없으면 `NULL`) | `'4n8...'` |
| **`youtube_url`** | TEXT | NULL 허용 | 공식 뮤직비디오(MV) URL (없으면 `NULL`) | `'https://youtu.be/...'` |
| **`song_id`** | INTEGER | NULL 허용, FK(`songs.id`) | 곡 마스터 연결 번호 (라이브 연동용) | `301` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 02:20:00+09` |

---

### ⑤ 가사 및 크레딧 테이블: `track_lyrics` (가사/발음/크레딧)

새 프론트엔드의 [오리곡 탭]에서 상세 조회 시 노출되는 가사 데이터입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `2001` |
| **`track_id`** | INTEGER | NOT NULL, UNIQUE, FK(`tracks.id` ON DELETE CASCADE) | 어느 트랙인가? (1:1 대응) | `2001` (과거를 먹는 자) |
| **`original_lyrics`**| TEXT | NOT NULL | 원문 가사 | `'くだらない日々に...'` |
| **`translation_ko`** | TEXT | NULL 허용 | 한국어 번역 가사 (없으면 `NULL`) | `'시시한 날들에...'` |
| **`pronunciation_ko`**| TEXT | NULL 허용 | 한국어 독음/발음 (없으면 `NULL`) | `'쿠다라나이 히비니...'` |
| **`lyricist`** | TEXT | NULL 허용 | 작사가 (모르면 `NULL`) | `'カンザキイオリ'` |
| **`composer`** | TEXT | NULL 허용 | 작곡가 (모르면 `NULL`) | `'カンザキイオリ'` |
| **`arranger`** | TEXT | NULL 허용 | 편곡가 (모르면 `NULL`) | `'カンザキイオリ'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 02:20:00+09` |

---

### ⑥ 커버 영상 테이블: `youtube_covers` (공식 커버 MV)

녹음과 편집을 거쳐 공식 업로드된 유튜브 커버 영상 메타데이터입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 커버 영상 고유 번호 | `301` |
| **`youtube_video_id`**| TEXT | NOT NULL, UNIQUE | 유튜브 11자리 영상 ID | `'abc123XYZ'` |
| **`title`** | TEXT | NOT NULL | 영상 제목 | `'【歌ってみた】Blessing covered by V.W.P'` |
| **`url`** | TEXT | NOT NULL | 유튜브 전체 주소 | `'https://youtu.be/...'` |
| **`published_at`** | TIMESTAMPTZ | NULL 허용 | 영상 공개 일시 (모르면 `NULL`) | `2023-08-15 19:00:00+09` |
| **`song_id`** | INTEGER | NULL 허용, FK(`songs.id`) | 무슨 원곡을 불렀는가? (모르면 `NULL`) | `402` (Blessing) |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 02:20:00+09` |

---

### ⑦ 커버 참여자 테이블: `cover_artists` (참여자 명단)

커버 영상에 참여한 아티스트들을 1명이든 10명이든 자유롭게 담는 연결 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 | 설명 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`cover_id`** | INTEGER | NOT NULL, FK(`youtube_covers.id` ON DELETE CASCADE) | 어느 커버 영상인가? | `301` (Blessing 커버) |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 참여 아티스트 번호 | `1` (카프), `2` (리메)... |
| **`is_main`** | BOOLEAN | NOT NULL, DEFAULT TRUE | 메인 업로더(채널 주인) 여부 | 채널 주인만 `TRUE`, 콜라보 게스트는 `FALSE` |

* **복합 기본키(PK)**: `(cover_id, artist_id)`
