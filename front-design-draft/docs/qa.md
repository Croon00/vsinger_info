# 검증 가이드와 결과

현재 설계는 [화면 설계](design-plan.md), 실제 API와 측정값은 [조회 API v2](../../docs/read-api-v2.md)를 따른다. 과거 단계마다 누적된 테스트 숫자와 폐기된 UI 설명은 제거했다. 아래 결과는 해당 날짜의 기록이며 이후 변경까지 자동 보장하지 않는다.

## 표준 검증

프론트 디렉터리에서 실행한다.

```powershell
npm test
npm run test:e2e
npm run test:integration
npm run build
```

| 검증 | 대상 | 외부 의존 |
| --- | --- | --- |
| npm test | 데이터 변환, 요청 캐시/취소, 검색·날짜·통계 | mock/fixture |
| test:e2e | 목업 PC·모바일, 탐색·검색·팝업·영상 시점·통계·캘린더·테마 | 플레이어는 테스트 더블 |
| test:integration | 실제 API 모드의 v2 응답 변환·화면 연결 | HTTP 응답 fixture, 실제 DB 없음 |
| build | Vue TypeScript 검사 + 실제 모드 Vite 빌드 | 실제 DB 없음 |
| build:mock | 목업 배포 빌드 | 실제 DB 없음 |

Playwright는 설치된 Chrome을 사용하며 다른 경로는 CHROME_PATH로 지정한다. mock 서버는 5195번, integration은 5196번이다. 결과도 test-results/mock, test-results/integration으로 분리한다.

백엔드 관련 회귀 테스트는 루트 가상환경에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_read_api.py tests/test_spotify.py tests/test_youtube_service.py tests/test_artist_identity.py -q
```

## 2026-09-18 조회 API v2 검증

- 백엔드 관련 회귀 테스트 30개 통과.
- 프론트 단위 테스트 24개, mock E2E 28개, API 계약 fixture E2E 2개 통과. 마지막 브라우저 테스트 명령은 정상 종료했다.
- TypeScript 검사·실제 모드 프로덕션 빌드·git diff --check 통과.
- 실제 Neon 연결: PC 1440px / 모바일 390px에서 라이브 첫 6개 → 더 보기 12개, 통계 10행, 캘린더를 확인했다. 확인 경로에서 API·런타임 오류와 가로 넘침이 없었다.
- 일반 8000번 API에서도 v2 아티스트 목록 200을 확인했다. 검증용 8001/5198 서버는 종료했다.
- DB 스키마·레코드 변경, Spotify 최초 실제 외부 요청 측정, 공개 배포 검증은 포함하지 않았다. 데이터 품질을 보증하는 검증도 아니다.

문서 정리에서는 프로그램 코드를 변경하지 않았다. 위 결과를 문서 정리 시점의 새로운 테스트 실행으로 간주하지 않는다.

## 수동 점검

홈·탐색·아티스트 네 탭·검색·뷰어·캘린더/리스트·설정·공연/가사 팝업을 PC/모바일 및 라이트/다크에서 확인한다.

- 긴 이름·이미지 실패에서도 카드 폭과 즐겨찾기 위치가 유지되는지.
- 검색어 Enter·뒤로가기·새로고침과 팝업 포커스 복귀가 일관적인지.
- 통계의 마지막 페이지에서도 문서 높이·스크롤·버튼 위치가 움직이지 않는지.
- 캘린더 5주/6주·다른 달·일정 넘침·모바일 스와이프·작은 화면 스크롤·독 여백이 유지되는지.
- 키보드 조작과 모션 감소 환경에서 정보와 기능이 빠지지 않는지.

성능 재측정은 API 문서의 benchmark/profile 도구를 사용한다. scripts/verify-live-read.mjs는 5198번 프론트·실제 아티스트 ID 2를 가정한 당시 환경 전용 도구다. 다른 환경에서는 URL·ID·아카이브 수 전제를 조정해야 한다.

## 과거 디자인·영상 검증 자료

2026-09-15 Luma CLI view 18종과 로컬 UI 135개를 대조했다. [레지스트리 기록](luma-registry-audit.json)은 당시 자료이며 현재 원격 레지스트리와 항상 같다는 의미는 아니다. 프로필 1:1·14px 반경, ToggleGroup 방향, Card 조합, 키보드 동작을 검수했다.

2026-09-16 디자인 점검은 320/390/900/1440px와 라이트·다크에서 수행했다. [screenshots](screenshots/)는 당시 자료다. 캘린더·검색·통계는 이후 변경되었으므로 오래된 캡처를 최신 사양으로 쓰지 않는다.

같은 날 실제 Chrome에서 목업 HACHI #182/#181/#171 영상의 재생 상태 1, 시간 증가와 디코딩 프레임 증가를 확인했다. #171은 1,088초 시작과 587초 세트리스트 이동도 확인했다. 모든 곡을 청취 검수한 결과는 아니다.

현재 뷰어는 자동재생을 요청하고 차단 시 음소거 재생을 시도한다. localhost와 Referrer-Policy를 사용하며 YouTube 헤더 위조·영상 프록시는 하지 않는다. 외부 네트워크·공개 상태·브라우저 정책에 따라 재생 가능 여부가 달라진다. 테스트 더블 성공을 실제 재생 성공으로 간주하지 않는다.

기존 scripts/check-video.mjs, inspect.mjs, design-audit.mjs는 과거 목업 ID·5174번 포트·일부 고정 개수를 전제로 한다. 특히 check-video는 아카이브 3개를 가정하여 확장된 목업과 다르므로 그대로 실행하는 표준 명령으로 안내하지 않는다. 필요한 환경·개수 전제를 수정한 뒤 사용한다. 이번 문서 정리에서는 도구 코드를 변경하지 않았다.
