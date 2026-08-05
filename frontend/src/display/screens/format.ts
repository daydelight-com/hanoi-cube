// 表示用の純関数(テスト対象)。

/** 残り時間 ms → "M:SS"(負値は 0:00 に丸める)。仕様§5.6: 1:00 からのカウントダウン */
export function formatRemaining(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 残り10秒未満の強調(ws-messages.md: 強調はクライアント判断) */
export function isTimeCritical(ms: number): boolean {
  return ms < 10_000
}
