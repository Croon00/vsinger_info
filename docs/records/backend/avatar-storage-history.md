# 프로필 이미지 저장 이력

현재 계약은 [프로필 이미지 저장과 교체](../../avatar-storage.md)를 따른다. 이 문서는 당시 날짜의 적용·검증·실데이터 처리 기록이며 수치는 기록 시점 값이다. 2026-11-23 계약 문서에서 분리했다.

## 2026-09-20 최초 이전

아티스트 이미지 파일은 Neon Object Storage, 대표 URL은 `artists.avatar_url`에 저장하도록 최초 적용했다.

81개 이미지 다운로드·WebP 생성·업로드·DB 반영 성공, 실패 0개. 각 3개 변형의 공개 응답과 캐시 헤더를 DB 반영 전에 확인했다. 원본 합계 13,153,829 bytes, 256px 합계 1,174,592 bytes(약 91% 감소). 전송 파일 크기 비교이며 페이지 전체 로딩 시간 측정값은 아니다.

로컬 fixture: 이미지 변환/URL 검사 및 기존 조회 API 테스트 12개, 프론트 단위 테스트 26개, PC·모바일 이미지 크기 선택/지연 로딩/주소 교체 브라우저 테스트 2개 통과. 프론트 타입 검사·프로덕션 빌드 통과.

## 2026-10-02 자동 초기 이미지

자동 초기 이미지 코드와 migration 007을 추가했다. 같은 날 운영 DB 읽기 전용 확인에서 SHIN·히비쿠의 작업 성공과 공개 이미지 응답을 확인했다. Figaro는 worker의 `missing_storage_configuration` 진단을 확인한 뒤 사용자 요청으로 정상 로컬 설정에서 작업 9를 수동 완료했다. 변환 이미지 3종과 대표 URL·감사 기록을 반영했다. 서버 worker 환경변수 갱신·재시작은 남아 있다.

disposable 로컬 PostgreSQL과 provider/S3/HTTP mock 검증 203개 통과. 범위는 신규 자동 이미지·등록 dry-run/재실행·동시 claim·lease 복구·provider 대기·수동 수정/소유 변경 보호·공개 업로드 검증, migration 001/002/004/006 업그레이드, 기존 이미지 CLI·runtime·음악 작업·YouTube/Spotify 수집·조회 API·X 클라이언트 회귀다. 운영 DB schema 변경·실제 YouTube/X 조회·업로드는 실행하지 않았다.

저장 오류 진단 보완: 로컬 disposable PostgreSQL·mock S3/HTTP 검증 42개 통과. 원본/변환 업로드 및 공개 응답 실패 단계, HTTP/S3 코드, 설정 누락, 비밀정보 제외, 재시도 소진 시 진단 보존과 성공 시 오류 제거, 기존 이미지 보호·runtime 회귀를 확인했다. 이 수정 검증에서는 운영 DB 변경이나 실제 업로드를 실행하지 않았다. 별도 승인된 앞선 실데이터 진단에서는 Figaro 원본 PUT 1회와 익명 GET이 성공했고 DB는 읽기 전용이었다. 과거 실패 예외는 복원하지 못했다.

Figaro 실데이터 수동 완료: 사용자 요청 범위인 아티스트 941만 처리했다. 이전 선택 원본을 같은 계정 snapshot에서 재사용했고 작업 9는 첫 시도에 `succeeded`로 종료됐다. 128/256/512 WebP 공개 GET은 모두 200이며 각각 5,790/17,742/42,810 bytes와 immutable 캐시 헤더를 확인했다. `artists.avatar_url`과 `initial-avatar-v1` 영수증을 반영했다. 기존 실패 작업은 보존했고 다른 아티스트·음악 수집·외부 알림은 실행하지 않았다. 서버 환경변수는 변경하지 않았다.

## 2026-10-03 요청 아티스트 점검

요청 아티스트 34명 읽기 전용 점검: Figaro·SHIN·히비쿠 3명은 이미지가 있고, 나머지 31명은 빈 이미지와 pending/retry 작업이다. 모두 YouTube owner 계정을 사용하며 이 31명에게 등록된 X 후보는 없다. 안나 작업 41의 실제 오류는 `quotaExceeded`다. 태평양 시간 자정 초기화에 맞춰 요청 대상의 pending/retry 31개 첫 실행 시각을 2026-10-03 16:00:30 KST로 앞당겼다. 우타와꾸 첫 재시도보다 30초 이르며 작업 예약 변경이지 이미지 저장 성공 기록은 아니다.

현재 로컬 `storage_settings()`에서는 endpoint·secret key·region이 없다(값은 기록하지 않음). API 한도가 풀려도 로컬 업로드에는 이 설정 복구가 필요하다. 이 확인에서 이미지 다운로드·업로드나 이미지 URL 변경은 수행하지 않았다. 배포 worker의 저장소 설정은 이번 확인으로 판단할 수 없다.

`avatar_jobs.py run-once/worker --artist-id ID`(반복 가능)로 요청 대상만 선점할 수 있게 했다. 인자를 생략하면 기존 전체 worker 동작이다. 요청 대상의 이미지 처리 transaction을 rollback하는 실데이터 검증으로 범위 선점을 확인했고 검증용 변경은 모두 되돌렸다. 관련 mock/fixture 테스트는 38 passed이며 로컬 PostgreSQL 부재로 DB fixture가 생략됐다.

## 2026-11-21 Figaro·shin 누락 파일 복구

실제 저장소에서 두 아티스트(ID 941·942)의 original·128/256px는 정상이고 대표 512px만 404였다. 화면별 이미지 선택에 따라 정상/실패가 달라질 수 있다. 파일이 사라진 경위는 이번 응답 확인만으로 확정할 수 없다. 로컬의 AVATAR_BUCKET 기본값과 저장 URL 버킷이 달라 avatar_variants가 빈 객체인 점도 확인했으나, 대표 URL 자체의 404를 먼저 복구했다.

`scripts/repair_requested_profiles_20261121.py`는 기본 dry-run이다. 저장 원본의 재변환이 기존 작은 이미지와 바이트 단위로 일치함을 확인하고 `--apply`에서 누락 512px만 조건부 업로드한다. 기존 사진·대표 URL은 유지했다. 파일 크기는 Figaro 42,810 bytes, shin 33,546 bytes이며 실제 128/256/512px 6파일 모두 공개 응답·WebP 디코딩을 확인했다. 영수증 9924에 복구 해시·경로를 남겼다. 반복 적용은 already_applied=true다. 관련 저장·URL fixture 19 passed, 브라우저 시각 검수는 수행하지 않았다.
