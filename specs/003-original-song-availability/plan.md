# 오리지널 곡 조회 복구 설계

FR-001: 분류 JSON을 `data/classification/`에서 `app/resources/classification/`으로 이동하고 `music_tags.CATALOG`와 테스트·계약 문서를 갱신한다. JSON 내용은 보존한다.

FR-002~FR-004: loader는 `FileNotFoundError`만 전용 `MusicTagCatalogUnavailable`로 변환하고 로그를 남긴다. service는 분류 필터가 없을 때만 빈 태그로 기존 repository를 호출한다. router는 분류 필터 요청의 전용 예외를 HTTP 503으로 변환한다. 누락을 캐시하지 않으며 기존 변경 시각 캐시를 유지한다.

검증: fixture에서 누락→복구와 HTTP 200/503을 검증하고 기존 곡 조회 테스트를 실행한다. 별도 읽기 전용 실DB 검증으로 실제 기본 조회의 응답 모델과 총수를 확인한다. 배포·DB 변경·수집·외부 전송은 수행하지 않는다.
