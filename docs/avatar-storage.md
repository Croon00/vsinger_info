# 프로필 이미지 저장과 교체

2026-09-20 적용. 아티스트 이미지 파일은 Neon Object Storage, 대표 URL은 기존 `artists.avatar_url`에 저장한다. 새 DB 테이블은 추가하지 않았다. 수집기·Discord 봇은 변경하지 않는다.

## 연결 설정

루트의 Git 제외 파일 `.env.catalog` 또는 서버 환경변수에 다음 값을 설정한다. 비밀값은 프론트 환경변수에 넣지 않는다.

- `NEW_CATALOG_DATABASE_URL`: 새 카탈로그 DB
- `AWS_ENDPOINT_URL_S3`: 해당 Neon 브랜치의 S3 endpoint
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: 저장소 자격 증명
- `AWS_REGION`: 저장소 리전
- `AVATAR_BUCKET`: 이미지 버킷. 이번 적용값은 `avator-image`

버킷은 Neon 콘솔에서 `public_read`로 설정해야 한다. 공개 읽기만 허용하며 쓰기는 자격 증명이 필요하다. 현재 코드는 별도 CDN을 구성하지 않고 저장소에서 직접 제공한다. 캐시는 HTTP 브라우저 캐시다.

## 크기 선택

현재 CSS 기준 즐겨찾기는 88/100/116px, 아티스트 상세는 80/140/168px, 공연 팝업은 최대 108px, 일정 목록은 48~64px이다. 탐색·검색 그리드는 컨테이너에 따라 가변이다.

| 파일 | 주된 용도 |
| --- | --- |
| 128.webp | 일정 목록·작은 프로필 |
| 256.webp | 즐겨찾기·모바일 그리드, 작은 프로필의 고밀도 화면 |
| 512.webp | 탐색 그리드·상세 프로필의 고밀도 화면 |
| original | 재가공용 원본, 일반 프론트에 제공하지 않음 |

픽셀 크기는 긴 변의 상한이다. 비율을 유지하고 원본보다 확대하지 않는다. EXIF 방향을 반영한 뒤 화면용 파일의 메타데이터를 제거하고 WebP quality 85로 저장한다. 애니메이션 이미지라면 첫 프레임을 정적 이미지로 사용한다.

`ArtistAvatar`가 실제 렌더링 크기와 devicePixelRatio에 맞는 파일 하나를 선택한다. 화면 200px 근처에 오기 전에는 src를 비워 Reka의 내부 사전 로딩도 지연한다. 실패 시 기존 AvatarFallback을 유지한다.

## 최초 이전 / 신규 URL 반영

프로젝트 루트에서 실행한다. report 경로는 실행마다 새 이름을 쓴다. 기존 보고서는 복구 이력이므로 prepare가 덮어쓰지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_avatars.py prepare --report db-migration/workspace/avatars/import-next.json
.\.venv\Scripts\python.exe scripts/migrate_avatars.py apply --report db-migration/workspace/avatars/import-next.json
```

prepare는 DB를 조회하고 외부 이미지를 로컬에 다운로드·가공한다. 이미 관리 중인 URL은 건너뛴다. apply는 원본과 변형 파일을 업로드하고 **모든 변형의 익명 GET, 내용, Cache-Control을 확인한 다음** DB를 갱신한다. 새 주소를 만든 동안 관리자가 avatar_url을 수정했다면 conflict로 건너뛴다. 다운로드/업로드 실패 항목의 DB URL은 유지한다. apply는 중단 후 같은 report로 재실행할 수 있다.

관리자에서 신규 외부 URL을 저장한 뒤 위 과정을 실행하거나, 한 아티스트만 교체할 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_avatars.py prepare --artist-id 1 --source-url "https://example.com/new-profile.jpg" --report db-migration/workspace/avatars/artist-1-next.json
.\.venv\Scripts\python.exe scripts/migrate_avatars.py apply --report db-migration/workspace/avatars/artist-1-next.json
```

관리자 화면에서 URL을 저장하는 것만으로 자동 업로드되지는 않는다. 현재 자동화 범위는 위 명시적 CLI 작업이다. 빈 avatar_url인 아티스트는 먼저 관리자에서 원본 주소를 등록한다.

## 캐시와 교체

경로는 `avatars/v1/{artist_id}/{콘텐츠 해시}/{128|256|512}.webp`다. 해시는 원본과 가공 결과에서 만들어 이미지나 가공 설정이 달라지면 새 경로가 된다.

- 이미지 헤더: `Cache-Control: public, max-age=31536000, immutable`
- DB 대표 URL: 512.webp
- API `avatar_variants`: 128/256/512 주소. 현재 설정의 관리 URL만 파생하고 외부 URL에는 빈 객체를 반환한다.
- API 응답은 기존 no-store, 프론트 데이터 캐시는 기존 30초다. 이미 열린 화면은 자동 push 갱신하지 않으며 새로고침하면 새 URL을 받는다.
- 이전 파일은 삭제하지 않는다. 브라우저 캐시나 복구 이력과 충돌하지 않는다.
- CDN/이미지 변환 서비스는 별도로 추가하지 않았다.

원본, 이전 주소, 새 주소와 결과는 Git 제외 경로 `db-migration/workspace/avatars/`에 보존한다. 복구 시 report의 source(교체 작업이면 previous_url)를 해당 ID에 복원하되, 현재 URL이 report의 new_url과 일치하는지 확인해야 한다. 이후의 별도 수정을 덮어쓰지 않는다.

## 검증 기록

2026-09-20: 81개 이미지 다운로드·WebP 생성·업로드·DB 반영 성공, 실패 0개. 각 3개 변형의 공개 응답과 캐시 헤더를 DB 반영 전에 확인했다. 원본 합계 13,153,829 bytes, 256px 합계 1,174,592 bytes(약 91% 감소). 전송 파일 크기 비교이며 페이지 전체 로딩 시간 측정값은 아니다.

로컬 fixture: 이미지 변환/URL 검사 및 기존 조회 API 테스트 12개, 프론트 단위 테스트 26개, PC·모바일 이미지 크기 선택/지연 로딩/주소 교체 브라우저 테스트 2개 통과. 프론트 타입 검사·프로덕션 빌드 통과.
