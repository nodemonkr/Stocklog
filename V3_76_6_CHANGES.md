# StockLog v3.76.6 변경사항

## 키움 동기화 무한대기 방지

- Kiwoom REST 단일 요청 gate의 취소 누수를 수정했습니다.
- gate 대기 중 취소된 coroutine이 queue에 남지 않도록 정리합니다.
- gate 획득 후 throttle 대기 중 취소되어도 반드시 gate를 반환합니다.
- gate 대기시간에 90초 상한을 두어 HTTP 요청 전 무한 대기를 방지합니다.
- Kiwoom runtime status에 현재 gate API ID, 점유시간, 대기 상한을 추가했습니다.

## 동기화 진단 로그 강화

통합 동기화 TXT에 아래 milestone이 추가됩니다.

- KIWOOM_RUNTIME_VALIDATE_START/DONE
- KIWOOM_ADMIN_LOAD_START/DONE
- KIWOOM_TOKEN_START/DONE/READY/FAILED
- KIWOOM_UNIVERSE_START/DONE
- UNIVERSE_KOSPI_START/DONE/FAILED
- UNIVERSE_KOSDAQ_START/DONE/FAILED
- UNIVERSE_KIND_START/DONE/FAILED
- KIWOOM_INDEX_START/DONE
- KIWOOM_PRICES_PROGRESS (첫 종목, 100종목 단위, 마지막)
- KIWOOM_METRICS_PHASE_START / KIWOOM_METRICS_PROGRESS
- KIWOOM_PART_DONE

따라서 예외가 발생하지 않는 정지 상황도 마지막 milestone으로 대기 지점을 확인할 수 있습니다.

## 회귀 테스트

- 취소된 gate waiter가 queue에서 제거되는지 검사하는 테스트를 추가했습니다.
- throttle 중 취소 시 active gate가 해제되는지 검사하는 테스트를 추가했습니다.
