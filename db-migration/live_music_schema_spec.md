> 이전 참고안입니다. 사용자 결정이 반영된 현재 기준은 [새 DB 전체 명세](새_DB_테이블_필드_명세.md)와 [DB 구조 계획](db-renewal-plan.md)입니다. 아래 원본의 크레딧·고정 게스트·역할 구분 등은 현재 사양으로 적용하지 않습니다.

﻿# 라이브 방송 및 곡·세트리스트 DB 스키마 사양서 (Live & Music Schema Spec)

기준일: 2026-09-19  
용도: schedule_music DB 리뉴얼 - 라이브 아카이브, 원곡자, 곡 마스터, 세트리스트 가창 기록 정규화 규격

---

## 1. 전체 구조 및 연결 관계 (Overview)

```text
[1. live_archives]          [4. live_song_performances]          [3. songs]
   방송 영상 카드                     부른 순간의 기록                    노래 마스터
(카프의 5월 1일 노래방송)  ───▶ (이 방송 15:30에 이 노래 부름!) ◀─── (Pretender)
                                 │       │          │                   │
                                 ▼       ▼          ▼                   ▼
                           performer_id  guest_id1  guest_id2   [2. original_artists]
                            (1: 카프)   (2: 리메)  (3: 하루)          원곡 가수
                            [메인 가창]  [게스트1]  [게스트2]     (Official髭男dism)
```

* **원곡자(`original_artists`) 분리**: 세상의 모든 원곡 가수/작곡가를 고유 ID로 등록하여 곡(`songs`)과 연결합니다.
* **콜라보 가창 지원**: 별도 연결 테이블 없이 `guest_artist_id1`, `guest_artist_id2` 2개 컬럼을 두어 **최대 3인(메인 1명 + 게스트 2명)** 가창까지 아주 깔끔하게 지원합니다.
* **곡 검색 별칭 제외**: `song_aliases`는 제외하고 `songs` 테이블의 3개 언어 표기(원어/한국어/영문)로 검색을 처리합니다.

---

## 2. 테이블 상세 사양

### ① 방송 테이블: `live_archives` (YouTube 라이브 아카이브)

아티스트가 진행한 노래방송(우타와쿠) 영상 자체의 정보를 담는 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `1001` |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id`) | 방송 메인 진행 아티스트 번호 | `1` (카프) |
| **`youtube_video_id`** | TEXT | NOT NULL, UNIQUE | 유튜브 고유 11자리 영상 ID | `'dQw4w9WgXcQ'` |
| **`title`** | TEXT | NOT NULL | 영상 원본 제목 | `'【歌枠】深夜のまったり歌配信【花譜】'` |
| **`url`** | TEXT | NOT NULL | 영상 전체 주소 | `'https://www.youtube.com/watch?v=...'` |
| **`broadcast_at`** | TIMESTAMPTZ | NULL 허용 | 실제 방송 시작 일시 (모르면 `NULL`) | `2024-05-01 20:00:00+09` |
| **`published_at`** | TIMESTAMPTZ | NULL 허용 | 영상 공개/업로드 일시 (없으면 `NULL`) | `2024-05-01 19:50:00+09` |
| **`duration_seconds`**| INTEGER | NULL 허용 | 영상 전체 길이 (초 단위, 모르면 `NULL`) | `7200` (2시간) |
| **`status`** | TEXT | NOT NULL, DEFAULT 'ready' | 세트리스트 상태 (`'ready'`, `'pending'`, `'no_setlist'`) | `'ready'` |
| **`top_comment`** | TEXT | NULL 허용 | 수집된 원본 고정댓글 전문 (없으면 `NULL`) | `'01:23 곡명...'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 01:40:00+09` |

---

### ② 원곡 아티스트 테이블: `original_artists` (원곡 가수 등록부)

세상의 모든 원곡 가수, 밴드, 보컬로이드 작곡가(P)를 딱 한 번씩만 등록해 두는 사전입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 원곡자 고유 번호 | `50` |
| **`name_native`** | TEXT | NOT NULL | 원어 공식 이름 | `'Official髭男dism'`, `'米津玄師'`, `'ツミキ'` |
| **`name_ko`** | TEXT | NULL 허용 | 한국어 표기 (없으면 `NULL`) | `'오피셜히게단디즘'`, `'요네즈 켄시'` |
| **`name_latin`** | TEXT | NULL 허용 | 영문/로마자 표기 (없으면 `NULL`) | `'Official HIGE DANDISM'`, `'Kenshi Yonezu'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 01:40:00+09` |

---

### ③ 곡 마스터 테이블: `songs` (고유 정규 곡 등록부)

세상에 존재하는 노래를 중복 없이 등록해 두는 곡 마스터 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 곡 고유 번호 | `501` |
| **`slug`** | TEXT | NOT NULL, UNIQUE | 영문 고유 식별 코드 | `'pretender-official-hige-dandism'` |
| **`title_native`** | TEXT | NOT NULL | 원어 공식 곡 제목 | `'Pretender'`, `'フォニイ'` |
| **`title_ko`** | TEXT | NULL 허용 | 한국어 통용 곡 제목 (없으면 `NULL`) | `'프리텐더'`, `'포니'` |
| **`title_latin`** | TEXT | NULL 허용 | 영문/로마자 곡 제목 (없으면 `NULL`) | `'Pretender'`, `'Phony'` |
| **`original_artist_id`**| INTEGER | NOT NULL, FK(`original_artists.id`) | 원곡 아티스트 번호 | `50` (Official髭男dism) |
| **`tj_number`** | TEXT | NULL 허용 | TJ 노래방 공식 번호 (미등록 시 `NULL`) | `'68123'` |
| **`ky_number`** | TEXT | NULL 허용 | 금영 노래방 공식 번호 (미등록 시 `NULL`) | `'44567'` |
| **`spotify_track_id`** | TEXT | NULL 허용 | 스포티파이 공식 음원 트랙 ID (없으면 `NULL`) | `'4G8N...'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 01:40:00+09` |

---

### ④ 세트리스트 가창 기록: `live_song_performances` (핵심 테이블)

"누가, 어느 방송의 몇 분 몇 초에, 어떤 노래를 불렀는가?"를 1곡 단위로 기록하는 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `8001` |
| **`archive_id`** | INTEGER | NOT NULL, FK(`live_archives.id` ON DELETE CASCADE) | 어느 라이브 방송인가? | `1001` (위 카프 방송) |
| **`song_id`** | INTEGER | NULL 허용, FK(`songs.id`) | 무슨 노래인가? (곡 매칭 전이면 `NULL`) | `501` (Pretender) |
| **`performer_id`** | INTEGER | NOT NULL, FK(`artists.id`) | **메인 가창자** (기본값: 방송 진행자) | `1` (카프) |
| **`guest_artist_id1`**| INTEGER | NULL 허용, FK(`artists.id`) | **게스트 1 (솔로 가창이면 `NULL`)** | `2` (리메) |
| **`guest_artist_id2`**| INTEGER | NULL 허용, FK(`artists.id`) | **게스트 2 (2인 이하 가창이면 `NULL`)** | `3` (하루사루히) |
| **`start_seconds`** | INTEGER | NOT NULL | 영상 시작 지점 (초 단위) | `930` (15분 30초 = 930초) |
| **`timestamp_text`** | TEXT | NOT NULL | 댓글 원본 타임스탬프 (화면 표시용) | `'15:30'` |
| **`raw_title`** | TEXT | NOT NULL | 댓글에 적혀있던 원본 곡명 (출처 보존용) | `'Pretender'` |
| **`raw_artist`** | TEXT | NULL 허용 | 댓글에 적혀있던 원본 가수 (출처 보존용) | `'Official髭男dism'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 등록 일시 | `2026-09-19 01:40:00+09` |

---

## 3. 실제 데이터 저장 시나리오 예시

### 시나리오 A: 카프(1번) 솔로 가창
* `performer_id`: 1 (카프)
* `guest_artist_id1`: `NULL`
* `guest_artist_id2`: `NULL`

### 시나리오 B: 카프(1번) & 리메(2번) 2인 듀엣 가창
* `performer_id`: 1 (카프)
* `guest_artist_id1`: 2 (리메)
* `guest_artist_id2`: `NULL`

### 시나리오 C: 카프(1번), 리메(2번), 하루사루히(3번) 3인 트리오 가창
* `performer_id`: 1 (카프)
* `guest_artist_id1`: 2 (리메)
* `guest_artist_id2`: 3 (하루사루히)
