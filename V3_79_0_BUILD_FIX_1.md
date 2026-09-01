# StockLog v3.79.0 Build Fix 1

## 수정 이유
`frontend/src/App.jsx`의 자동매매 실패 학습 카드에서 JavaScript의 nullish coalescing(`??`)과 logical OR(`||`)를 괄호 없이 한 식에 혼용해 Vite/esbuild production build가 실패하는 문제가 있었습니다.

오류 예시:
`Cannot use "||" with "??" without parentheses`

## 수정 내용
- 문제 식을 `Number(x.realized_return_pct ?? x.current_return_pct ?? 0)` 형태로 변경했습니다.
- 자동매매 진단/경험학습 기능 자체의 동작 로직은 변경하지 않았습니다.
- backend 및 mobile 기능은 변경하지 않았습니다.

## 검증
- frontend JS/JSX TypeScript parser 검사: 오류 0건
- backend Python compileall: PASS
- restart-all.sh / restart-mobile.sh shell syntax: PASS

## 서버 적용
핫픽스는 기존 `Stocklog/frontend/src/App.jsx`만 교체하면 됩니다. 적용 후 루트에서 `./restart-all.sh`를 실행하십시오.
