# 멀티뷰 멤버십 채널 등록 준비

2026-11-24 사용자 요청으로 두 채널의 고정 ID와 연결할 기존 그룹을 확인했다.

| 채널 | YouTube 채널 ID | 그룹 |
| --- | --- | --- |
| [VESPERBELL MEMBERSHIP](https://www.youtube.com/channel/UCIZdHFI1j5glJBzYJrH99pw) | `UCIZdHFI1j5glJBzYJrH99pw` | `vesperbell` |
| [KMNCLUB](https://www.youtube.com/channel/UC68J5pWEshmwhDH45qnpIsg) | `UC68J5pWEshmwhDH45qnpIsg` | `kmnz` |

등록 스크립트는 기존 그룹·계정 소유권을 확인하고 두 채널에 멀티뷰 수집 상태를 설정한다. 신규 계정은 일반 영상 수집을 끈 상태로 등록한다. 기존 계정의 일반 수집 상태와 그룹의 카탈로그 공개 범위는 보존한다.

2026-11-24 격리 PostgreSQL을 포함한 `tests/test_multiview.py`, `tests/test_holodex.py`, `tests/test_youtube_live_monitor.py`의 테스트 49건이 통과했다. 두 채널의 반복 등록, Holodex·YouTube 수집 자격과 스냅샷 저장, 멀티뷰 조회, 카탈로그 공개 범위를 확인했다. 제공자 응답은 fixture를 사용했다.

운영 등록은 로컬 `DATABASE_URL`의 PostgreSQL 비밀번호 인증 실패로 커밋되지 않았다. 운영 DB 연결이 가능해지면 `python scripts/register_multiview_channels.py --apply`로 등록하고 새 조회·감시 코드에서 관측 여부를 확인한다. 실제 방송 발견과 재생은 아직 확인하지 않았다.
