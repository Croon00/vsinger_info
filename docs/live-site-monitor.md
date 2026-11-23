# 공개 라이브 일정 수집

공식 사이트에 공개된 공연 일정을 신규 DB의 `concerts`에 저장해 달력과 공연 상세 화면에 제공한다. 2026-11-23 README에서 분리했다. 이 문서는 코드 기준의 동작 설명이며, 실제 운영 수집 결과를 새로 검증한 기록은 아니다.

## 실행

| 방법 | 동작 |
| --- | --- |
| `python -m app.runtime` | `LIVE_SITE_MONITOR_ENABLED=true`(코드 기본값 true)이면 시작 직후와 이후 24시간마다 실행 |
| `python -m app.agents.live_site_monitor` | 한 번만 수집하고 처리 건수를 출력. DB에 저장하므로 실행 범위를 확인한다 |

`DATABASE_URL`이 없으면 수집하지 않는다. 구현은 [`app/agents/live_site_monitor.py`](../app/agents/live_site_monitor.py)와 [`app/integrations/live_site_pages.py`](../app/integrations/live_site_pages.py), 저장은 [`app/repositories/public_lives.py`](../app/repositories/public_lives.py)다.

## 대상

- Z-aN 채널: RK Music(`rkmusic`)과 카미츠바키 계열(`virtual_kaf`, `RIM_virtual`, `KOKO__virtual`, `harusaruhi`, `isekaijoucho`)
- RIOT MUSIC ZAIKO 채널
- RIOT MUSIC 공식 공지(`riot_info`, `mugensho_info`)와 이전 목록 페이지

소스마다 목록 페이지를 최대 10쪽까지 따라가며 공식 채널에 남은 과거 공연도 수집한다.

## 저장 기준

- 날짜와 카탈로그 아티스트를 확인한 일정만 저장한다. 아티스트가 일치하지 않으면 로그만 남기고 저장하지 않는다.
- 같은 원문 URL은 중복 등록하지 않는다. 지난 공연은 `completed`로 표시한다.
- 처리 결과는 `sources`, `details`, `created`, `failed` 건수로 로그에 남긴다.

## 제한

- robots.txt가 허용하지 않거나 사이트가 접근을 거부하면 해당 페이지를 건너뛴다.
- ZAIKO는 자동 요청에 403을 반환할 수 있다. RIOT 공식 공지를 보조로 확인하지만 일부 일정은 누락될 수 있다.
- 티켓 구매·응모는 수행하지 않고 공식 사이트 링크만 제공한다.

## 테스트

페이지 파싱은 `tests/test_live_site_pages.py`의 fixture로 검증한다. 실제 사이트 요청은 테스트에서 하지 않는다.
