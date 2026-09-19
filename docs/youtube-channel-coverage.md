# 누락 YouTube 채널 보완

2026-09-18에 기존 아티스트와 수집 채널을 별칭까지 대조하고, 공식 사이트에서
확인한 누락 채널을 아래 시드에 기록했다. 각 항목의 `source_url`은 공식 채널의
확인 근거이며 `channel_url`은 수집에 사용할 주소다.

적용 결과: 누락 모니터 20개를 DB에 추가해 전체 활성 채널이 27개에서 47개로
늘었다. 재실행 미리보기에서는 20개 모두 `already_registered`로 확인했다.
과거 영상 전체 수집은 이번 등록 작업에 포함하지 않았다.

- `data/seeds/rkmusic_missing_youtube_channels.json`: CONA, Diα, 妃玖, wouca,
  HONK THE HORN, NUROJUNK (6개).
- `data/seeds/kamitsubaki_missing_youtube_channels.json`: 花譜, 理芽, 春猿火,
  ヰ世界情緒, 幸祜, CIEL, ASU, VALIS, 佳鏡院, 御莉姫, 硝子宮, 美古途,
  夕凪機, 氷夏至 (14개).

RIM의 공식 프로필이 연결한 `/c/RIM_virtual` 주소는 해당 YouTube 페이지의
canonical 채널 ID로 변환했다. 원래 주소는 `original_channel_url`로 보존한다.
VALIS의 공식 프로필에 기재된 활동 휴지 상태는 시드의 `note`에 기록했다.

## 실행

```powershell
python scripts/register_missing_youtube_channels.py
python scripts/register_missing_youtube_channels.py --apply
```

기본 실행은 DB를 변경하지 않고 YouTube API로 공식 채널과 중복 여부를 확인한다.
`--apply`는 아직 없는 모니터만 `system:catalogue` 소유로 등록한다. 별칭으로
등록된 아티스트와 여러 이름에서 공유하는 채널을 중복 추가하지 않으며,
기존 소유자나 비활성 설정을 변경하지 않는다. 단일 목록은 `--seed 경로`로 지정한다.

이 스크립트는 채널 등록만 수행한다. 등록한 채널의 영상은 정규 수집 실행 때
처리하며, 과거 우타와꾸 수집은 기존 `scripts/backfill_youtube_channel.py` 또는
웹의 수집 버튼을 사용한다. 등록 자체는 Discord 알림이나 Calendar 일정을 만들지 않는다.

## 남은 확인 대상

- Cil, MEMESIA, NOiTA: 이번 조사에서 등록에 사용할 현재 공식 채널 근거를
  충분히 확인하지 못했으므로 추가하지 않았다.
- OTOUSAN, MEDACHI: 기존 아티스트의 서브 계정과 독립 채널인지 확인이 필요하다.
- KMNZ·VESPERBELL 멤버는 기존 그룹 채널을 공유하므로 개별 모니터를 중복 생성하지 않는다.
- MOCO, BAMBI, SAKUYA, KAGURA는 개별 채널을 확인하지 않았다.
  이번 등록 목록에는 HONK THE HORN과 NUROJUNK의 공식 그룹 채널이 포함된다.

## 검증

```powershell
python -m pytest tests/test_register_missing_youtube_channels.py tests/test_youtube_service.py tests/test_youtube_channel_monitor.py tests/test_artist_identity.py -q
```

등록 미리보기의 무변경 동작, 재실행 중복 방지, 비활성 설정 보존, 실패 격리와
실제 비동기 과거 수집 호출을 mock으로 검증한다.
