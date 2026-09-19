> 이전 참고안입니다. 사용자 결정이 반영된 현재 기준은 [새 DB 전체 명세](새_DB_테이블_필드_명세.md)와 [DB 구조 계획](db-renewal-plan.md)입니다. 아래 원본의 크레딧·고정 게스트·역할 구분 등은 현재 사양으로 적용하지 않습니다.

﻿# 아티스트 DB 스키마 사양서 (Artist DB Schema Specification)

기준일: 2026-09-19  
용도: schedule_music DB 리뉴얼 - 아티스트 및 관련 데이터 정규화 규격

---

## 1. 개념 구분: 소속사(Agency) vs 그룹(Group)

* **소속사(Agency)**: 아티스트들이 소속된 **기획사/회사/레이블** (예: `KAMITSUBAKI STUDIO`, `RK Music`, `RIOT MUSIC`)
  * 회사는 가수가 아니므로 `artists` 테이블의 `agency` 컬럼에 텍스트로 저장됩니다.
* **그룹(Group / Unit)**: 실제로 앨범을 내고 공연을 하는 **음악 팀/유닛** (예: `V.W.P`, `KMNZ`, `VESPERBELL`)
  * 그룹 자체도 노래를 부르고 방송을 하므로 `artist_type='group'`인 아티스트로 등록됩니다.
* **멤버(Member)**: 그룹에 속한 **개인 아티스트** (예: `카프`, `리메`, `티나`, `네로`)
  * `artist_group_members` 테이블을 통해 **그룹과 개인 멤버**가 연결됩니다.

---

## 2. 테이블 상세 사양

### ① 메인 테이블: `artists` (아티스트 기본 정보)

아티스트(개인 및 그룹)의 핵심 정보를 저장하는 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 / 기본값 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `1` |
| **`slug`** | TEXT | NOT NULL, UNIQUE | 영문 고유 식별 코드 (URL용) | `'kaf'`, `'kmnz'`, `'vwp'` |
| **`name_native`** | TEXT | NOT NULL | 원어 공식 이름 | `'花譜'`, `'KMNZ'` |
| **`name_ko`** | TEXT | NOT NULL | 한국어 공식 표기 | `'카프'`, `'케이엠엔지'` |
| **`name_latin`** | TEXT | NOT NULL | 영문/로마자 공식 표기 | `'KAF'`, `'KMNZ'` |
| **`artist_type`** | TEXT | NOT NULL (기본: `'vtuber'`) | `'vtuber'`, `'singer'`, `'group'` 중 하나 | `'vtuber'`, `'group'` |
| **`agency`** | TEXT | NULL 허용 | 소속사/기획사명 (개인세는 `NULL`) | `'KAMITSUBAKI STUDIO'`, `'RK Music'` |
| **`birthday_month`**| SMALLINT | NULL 허용 | 생일 월 (1 ~ 12, 모르면 `NULL`) | `1` |
| **`birthday_day`** | SMALLINT | NULL 허용 | 생일 일 (1 ~ 31, 모르면 `NULL`) | `15` |
| **`debut_date`** | DATE | NULL 허용 | 데뷔일 (`YYYY-MM-DD`, 모르면 `NULL`) | `'2018-10-18'` |
| **`bio`** | TEXT | NULL 허용 | 프로필 소개글 (없으면 `NULL`) | `'KAMITSUBAKI 소속 버추얼 싱어'` |
| **`theme_color`** | TEXT | NULL 허용 | 상징 헥스 컬러코드 (없으면 `NULL`) | `'#1A3B8B'` |
| **`avatar_url`** | TEXT | NULL 허용 | 프로필 이미지 URL (없으면 `NULL`) | `'https://.../kaf.jpg'` |
| **`created_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 최초 등록 일시 | `2026-09-19 00:50:00+09` |
| **`updated_at`** | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 최종 수정 일시 | `2026-09-19 00:50:00+09` |

* **참고**: `display_name`, `review_status`, `review_notes`는 DB에 저장하지 않습니다.
  * 표시 형태는 프론트엔드가 3개 언어 필드를 조합해 렌더링합니다.
  * 검토/승인 상태 및 작업 메모는 로컬 검토 도구(임시 파일)에서만 다룹니다.

---

## 3. 별칭 테이블: `artist_aliases` (검색 키워드)

검색창에 입력될 수 있는 오타, 약칭, 비공식 별명 등을 관리합니다. (`artists`와 1:N)

| 컬럼명 | 데이터 형태 | 제약조건 | 설명 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `101` |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 연결된 아티스트 번호 | `1` |
| **`alias`** | TEXT | NOT NULL | 검색용 별칭 문자열 | `'화보'`, `'꽃보'`, `'카후'` |

---

## 4. 외부 소스 테이블: `artist_sources` (수집 채널)

YouTube, X(트위터), Spotify 등 자동 수집 대상 채널들을 관리합니다. (`artists`와 1:N)

| 컬럼명 | 데이터 형태 | 제약조건 | 설명 및 비어있을 때(None) 규칙 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | INTEGER | PRIMARY KEY (자동증가) | 고유 번호 | `201` |
| **`artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 연결된 아티스트 번호 | `1` |
| **`platform`** | TEXT | NOT NULL | 플랫폼 구분 (`'youtube'`, `'x'`, `'spotify'`) | `'youtube'` |
| **`platform_id`** | TEXT | NULL 허용 | 플랫폼 내부 고유 ID (모르면 `NULL`) | `'UC--zuEfONeFXPvLqX0Kvbuw'` |
| **`handle`** | TEXT | NULL 허용 | 유저명/핸들 (없으면 `NULL`) | `'@virtual_kaf'`, `'virtual_kaf'` |
| **`url`** | TEXT | NOT NULL | 채널 전체 웹 주소 | `'https://youtube.com/@virtual_kaf'` |
| **`is_active`** | BOOLEAN | NOT NULL, DEFAULT TRUE | 자동 수집 활성화 여부 | `TRUE` / `FALSE` |

---

## 5. 그룹-멤버 연결 테이블: `artist_group_members` (유닛 소속)

음악 그룹(유닛)과 개인 멤버를 연결하는 매핑 테이블입니다.

| 컬럼명 | 데이터 형태 | 제약조건 | 설명 | 예시 |
| :--- | :--- | :--- | :--- | :--- |
| **`group_artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 그룹의 아티스트 ID (`artist_type='group'`) | `10` (KMNZ의 ID) |
| **`member_artist_id`** | INTEGER | NOT NULL, FK(`artists.id` ON DELETE CASCADE) | 멤버의 아티스트 ID (`artist_type='vtuber'`) | `11` (NERO의 ID) |

* **복합 기본키(PK)**: `(group_artist_id, member_artist_id)` 조합으로 중복 등록 방지.
