# StockLog v3.61.0 적용 방법

```bash
cd /home/conda/Stocklog
./restart-all.sh
```

적용 후 브라우저에서 `Ctrl + Shift + R`로 새 번들을 불러옵니다.

백엔드 시작 시 기존 `users` 테이블에 아래 컬럼이 없으면 자동으로 추가됩니다.

- `last_login_at DATETIME NULL`
- `last_login_method VARCHAR(20)`
- `login_count INT`

별도 수동 ALTER TABLE은 필요하지 않습니다.
