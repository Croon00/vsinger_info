# HONK THE HORN·NUROJUNK 멤버별 수집 보완

2026-11-22 사용자 요청으로 신규 DB·로컬 조회 API에 반영했다. [013 요구·설계·작업](../specs/013-shared-member-catalog/spec.md)을 따른다. legacy DB·계정 소유권·기존 세트리스트를 삭제하지 않았고 모델·Discord·Calendar를 호출하지 않았다.

## 조사와 결과

HONK THE HORN(계정 57, UCQXuGcIoseWY5HmW6-U7teg) 공개 업로드 182개, NUROJUNK(계정 25, UCuvYHCPdMxfvjW_F9w5LmRA) 153개를 API로 확인했다. 명시적 커버 후보는 각각 50/50·54/54개 저장되어 누락 0개다. Shorts 후보를 포함한 저장 수이며 화면의 본편 커버 수와 다르다.

| 멤버 | 라이브 | 본편 커버(듀엣·공동 포함) |
| --- | ---: | ---: |
| MOCO(40) | 23 | 9 |
| BAMBI(41) | 15 | 8 |
| SAKUYA(42) | 12 | 10 |
| KAGURA(43) | 14 | 10 |

개인 명의 21곡·그룹 듀엣 4곡·공동 커버 2곡, 총 27개 본편 영상이다. 공동 영상은 여러 개인 목록에서 공유되므로 개인 수를 합산해 전체 곡 수로 쓰지 않는다. aa0zL9BKGhI(パンダヒーロー), hhlxsAMb8F0(女々しくて)는 공식 공동 재생목록과 설명 MC/Vocal을 확인해 네 멤버에게 표시한다. 실제 publisher·영상 ID는 유지한다. 이름 없는 연습 음원·Shorts를 개인 본편 목록에 억지 배정하지 않는다.

cover 64행·출처 영상 63개를 추가하고, 과거 커버 프리미어의 빈 출처 1개를 정확한 publisher로 채웠다(감사 10476/10478). HONK 38개·NUROJUNK 24개 방송의 진행자/멤버 가창을 연결했다(10477/10479). 합동 방송은 두 멤버를 연결한다. 그룹 owner·기존 가창은 보존하며 타 가창자가 지정된 곡은 덮어쓰지 않는다. 저장된 세트리스트를 재사용했고 댓글을 다시 수집하지 않았다.

## 근거와 남은 범위

추가 사용자 결정으로 HONK 공식 채널 커버의 미표기 기본값을 변경했다. 제목에 MOCO 또는 BAMBI 한 명이 있으면 그 멤버에게만, 둘 다 있거나 둘 다 없으면 두 멤버에게 표시한다. 이름의 부분 일치는 사용하지 않는다. 다른 협업자 이름만 있는 경우에도 MOCO/BAMBI 미표기 기본값을 적용한다. NUROJUNK 및 라이브 진행자 판정은 별도 계약을 유지한다. 본편만 표시하도록 재확인했으므로 HONK의 Shorts 38개는 목록에 넣지 않는다. 현재 HONK 본편 12개는 이미 개인/검토 듀엣으로 연결되어 이번 일반화 뒤에도 개인 표시 수치는 9/8이다(다른 채널의 공동 영상 1개씩 포함).

HONK는 공식 MOCO/BAMBI STREAMS 목록으로 나눈다. NUROJUNK에는 같은 개인별 STREAMS 목록이 없어 공식 썸네일·제목을 개별 검토한 24개 방송을 사용했다. [검토 manifest](../migrations/catalog/nurojunk-stream-members-2026-11-22.json)에 영상/썸네일 URL·당시 이미지 SHA-256·명의를 보존했다. 향후 썸네일을 자동 얼굴 인식하지 않으며 명시적 진행자 제목 외에는 검토 대상이다. 공통 SNS·다른 멤버 상품 이름은 근거가 아니다.

HONK 2ceIEfZ8rR4, NUROJUNK ITHQE7YrLz8·V2JXCTh6ens는 개인 진행자 근거가 부족해 그룹 상태로 남겼다. 네 개인 라이브/통계에서는 외부 원곡 MV·커버 프리미어를 제외하지만 기존 import 원문·외부 ID는 보존한다. 전역 검색의 과거 데이터 전체를 새로 정정한 작업은 아니다.

관련 Python 86 passed, 76 skipped(disposable PostgreSQL 부재). 실제 신규 DB/로컬 HTTP 200 검증과 fixture는 별개다. 캐시·원문·검증은 outputs/honk-members-2026-11-22와 outputs/nurojunk-members-2026-11-22에 있다. 비공개/삭제·제목 근거가 없는 모든 커버의 완전 발견을 보장하지 않는다.

최종 로컬 HTTP 대조에서 네 멤버 커버 9/8/10/10개, 공동 영상 두 개의 네 멤버 노출, 개인 목록 내 중복 없음과 HTTP 200을 확인했다. 두 그룹의 반영 CLI 재실행은 각각 inventory_changes=0, members.changed=0으로 추가 저장이 없었다.

일일 poll·collect 재대조 코드를 연결하고 로컬 API를 재시작했다. 운영 worker/API 배포와 일일 실행 확인은 미완료다. 명시적 보완 CLI는 scripts/repair_shared_youtube_members.py --input PATH --group honk-the-horn 또는 nurojunk이며, --apply가 실제 반영이다.
