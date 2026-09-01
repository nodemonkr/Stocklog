export const n = (value: unknown) => Number(value || 0) || 0;

export const won = (value: unknown) => {
  const x = n(value);
  return `${Math.round(x).toLocaleString('ko-KR')}원`;
};

export const compactWon = (value: unknown) => {
  const x = n(value);
  const abs = Math.abs(x);
  if (abs >= 1_0000_0000_0000) return `${(x / 1_0000_0000_0000).toFixed(1)}조`;
  if (abs >= 1_0000_0000) return `${(x / 1_0000_0000).toFixed(1)}억`;
  if (abs >= 1_0000) return `${(x / 1_0000).toFixed(1)}만`;
  return Math.round(x).toLocaleString('ko-KR');
};

export const pct = (value: unknown, digits = 2) => {
  const x = n(value);
  const sign = x > 0 ? '+' : '';
  return `${sign}${x.toFixed(digits)}%`;
};

export const qty = (value: unknown) => {
  const x = n(value);
  const sign = x > 0 ? '+' : '';
  const abs = Math.abs(x);
  if (abs >= 1_000_000) return `${sign}${(x / 1_000_000).toFixed(1)}백만주`;
  if (abs >= 10_000) return `${sign}${(x / 10_000).toFixed(1)}만주`;
  return `${sign}${Math.round(x).toLocaleString('ko-KR')}주`;
};

export const dateTime = (value: unknown) => {
  if (!value) return '-';
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export const publicText = (value: unknown) => String(value || '')
  .replace(/Google AI Studio/gi, 'StockLog Gbot')
  .replace(/\b(?:Gemini|Ollama)(?:[-_.\w]*)\b/gi, 'StockLog Gbot')
  .replace(/StockLog Obot|\bObot\b/gi, 'StockLog Gbot');

export const errorText = (error: unknown) => {
  if (error && typeof error === 'object' && 'message' in error) return publicText((error as any).message || '오류가 발생했습니다.');
  return publicText(error || '오류가 발생했습니다.');
};
