# schedule_music · Front Design Draft

기존 프론트와 독립적으로 제작한 Vue 디자인 테스트 앱입니다. 아티스트를 찾고, 라이브의 특정 곡으로 이동하고, 공연과 생일을 살펴볼 수 있습니다.

## 실행

Node.js 22.12 이상 또는 24와 npm을 사용합니다. 이 디렉터리에서 실행하세요.

```powershell
npm install
npm run dev
```

접속: [http://127.0.0.1:5174](http://127.0.0.1:5174)

이 PC에서 nvm 프록시가 `No active Node configured`를 출력하면 현재 터미널에서만 다음 경로를 먼저 설정할 수 있습니다.

```powershell
$env:PATH = 'C:\Users\Homin\AppData\Local\nvm\installs\v24.21.0;' + $env:PATH
npm.cmd run dev
```

실행에 백엔드 서버, DB, API 키는 필요하지 않습니다. `localhost` 또는 `127.0.0.1`에서 Service Worker를 허용하는 브라우저를 사용하세요. 다른 장치에서 HTTP IP 주소로 접근하면 MSW가 요구하는 보안 컨텍스트가 충족되지 않을 수 있습니다.

## 구현 화면

- 홈: 통합검색과 즐겨찾는 아티스트. 즐겨찾기는 브라우저에 저장됩니다.
- 탐색: 공식 이미지의 아티스트 12팀, 한국어·원어·영문 이름 검색, 소속사 필터.
- 아티스트 상세: 라이브, 오리곡, 공연 정보 탭. 앨범별 곡 목록과 예시 가사, 예정 공연과 과거 타임라인.
- 라이브 뷰어: 실제 YouTube IFrame API, 클릭 가능한 세트리스트, `?t=` 시점 공유 및 새로고침 복원.
- 캘린더: 오프라인 공연과 멤버별 생일, 월 이동, 종류 필터, 즐겨찾기/전체 범위.
- 설정: 시스템·라이트·다크 테마. 기기 테마 변경에 반응하며 명시적 선택은 저장됩니다.

PC는 좌측 사이드바, 태블릿은 아이콘 사이드바, 모바일은 하단 독을 표시합니다. 가사·공연 상세는 PC Dialog와 모바일 Drawer를 사용하며, URL 직접 접근·뒤로가기·Escape·포커스 복귀를 지원합니다.

## 살펴보기

| 예시 | 주소 |
| --- | --- |
| 원곡 아티스트 검색 | [/search?q=요루시카](http://127.0.0.1:5174/search?q=요루시카) |
| 같은 곡을 부른 HACHI·세토노 토토 비교 | [/search?q=각성](http://127.0.0.1:5174/search?q=각성) |
| 곡의 시작 시점 | [/lives/101?t=1088](http://127.0.0.1:5174/lives/101?t=1088) |
| 디스코그래피 | [/artists/2?tab=originals](http://127.0.0.1:5174/artists/2?tab=originals) |
| 가사 팝업 직접 접근 | [/artists/1?tab=originals&lyrics=201](http://127.0.0.1:5174/artists/1?tab=originals&lyrics=201) |

## 데이터와 API

화면은 `src/api/client.ts`의 `fetch`만 사용하고, `src/mocks/handlers.ts`의 MSW가 응답합니다. worker 시작 이후 앱을 마운트합니다. 처리되지 않은 `/api/*` 요청은 501로 차단합니다. 개발용 서버 프록시는 없습니다.

초안 화면의 추가 필드는 `/api/draft/*`에서 제공합니다. 기존 백엔드의 일부 필드를 참고한 `/api/artists`, `/api/event-candidates`, `/api/songs/:id/lyrics` 예시도 포함합니다. 이 목업은 기존 백엔드 전체 계약의 구현이 아니며, 백엔드 연동 전에는 `docs/design-plan.md`의 매핑을 바탕으로 별도 adapter가 필요합니다.

| GET 경로 | 용도 |
| --- | --- |
| `/api/draft/artists`, `/api/draft/artists/:id` | 아티스트 목록·상세 |
| `/api/draft/lives?artist_id=...`, `/api/draft/lives/:id` | 아카이브 목록·세트리스트 |
| `/api/draft/albums?artist_id=...` | 앨범과 트랙 |
| `/api/draft/concerts` | 가상 오프라인 공연 |
| `/api/draft/search?q=...` | 아티스트와 세트리스트 검색 |
| `/api/songs/:id/lyrics` | 직접 작성한 예시 가사 |

아티스트 12팀, 라이브 영상 6개(그중 공식 다이제스트 1개), 세트리스트 25곡, 앨범·싱글 4개, 가상 공연 27개를 제공합니다. 콘텐츠가 없는 아티스트에서는 빈 상태를 확인할 수 있습니다. 공연 날짜는 방문 날짜에 맞춰 생성되어 지난 공연과 예정 공연이 함께 표시됩니다.

실제 영상·아티스트 정보의 출처는 [콘텐츠 출처](docs/content-sources.md)에 기록했습니다. **공연과 가격은 가상이며, 가사는 직접 작성한 예시입니다.** 아티스트·앨범 이미지는 공식 사이트 자산을 로컬에 보관했습니다. 실제 영상 재생과 썸네일, Google Fonts에는 인터넷 연결이 필요합니다. 영상 자체는 다운로드하거나 재배포하지 않습니다.

## 상태 시나리오

주소 뒤에 다음 query를 붙입니다. 제품 설정 UI에는 노출하지 않습니다.

- `/explore?scenario=slow`: 1.8초 지연으로 Skeleton 확인.
- `/explore?scenario=empty`: 빈 목록.
- `/explore?scenario=error`: API 503과 재시도.
- `/explore?scenario=broken-images`: Avatar fallback.
- `/artists/9999`: 존재하지 않는 콘텐츠.

정상 화면으로 돌아가려면 `scenario`를 제거하고 새로고침하세요. 즐겨찾기·테마·캘린더 범위는 `schedule-music-draft:` 접두사의 localStorage 키에만 저장합니다.

## 디자인 스킬

- 프로젝트 로컬 `.agents/skills/shadcn-vue`: `a2vfHFI`를 CLI에 실제 전달해 초기화했습니다. 생성된 `components.json`, Neutral 토큰, `reka-luma`, Inter, Lucide를 기반으로 합니다.
- 프로젝트 로컬 `.agents/skills/transitions-dev`: 즐겨찾기 아이콘 전환과 모션 토큰에 적용했습니다. 팝업 구조·접근성·테마에는 shadcn-vue를 우선합니다.
- `prefers-reduced-motion`에서는 이동·전환을 줄입니다.

## 검증

```powershell
npm test           # 검색, 날짜 경계, 생일 반복, 시점 검증
npm run test:e2e   # PC·모바일 주요 사용자 동작
npm run build     # TypeScript + 배포용 정적 빌드
npm run screenshots
```

E2E는 설치된 Chrome을 사용합니다. 다른 환경에서는 `CHROME_PATH`를 실행 파일의 절대 경로로 설정하세요. `screenshots`와 `check:video` 명령은 개발 서버 실행 후 사용합니다. YouTube API 호출 테스트는 외부 재생 제한과 무관하게 재현하도록 테스트 더블을 사용합니다. 실제 영상 검증의 환경상 제한은 [QA 기록](docs/qa.md)에 구분했습니다.

`dist`를 정적 서버에 올릴 때는 `/mockServiceWorker.js`를 포함하고, SPA 경로를 `index.html`로 fallback해야 합니다. 이 작업에서 외부 배포는 하지 않았습니다.
