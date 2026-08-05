// 待機ランキングのせり上がり時間。サーバーのタイマー
// (server/app/state/machine.py の IDLE_RANKING_*)と同じ式・同値に保ち、
// 演出の終了とサーバーのタイムアウトを一致させる。

export const IDLE_RANKING_ROW_MS = 1_000
const SCROLL_MIN_MS = 2_000
const SCROLL_MAX_MS = 27_000

export function idleRankingScrollMs(rows: number): number {
  return Math.min(Math.max(rows * IDLE_RANKING_ROW_MS, SCROLL_MIN_MS), SCROLL_MAX_MS)
}

/**
 * せり上がり中の rank_tick の再生時刻(ms)。1行=1秒のせり上がりに合わせて
 * 1秒ごとに刻み、終端(=1位到達。fanfare の再生時刻)の手前まで(§5.12
 * 「1行ごとのティック、1位表示でファンファーレ」)。
 */
export function idleRankingTickTimes(rows: number): number[] {
  const end = idleRankingScrollMs(rows)
  const times: number[] = []
  for (let t = IDLE_RANKING_ROW_MS; t < end; t += IDLE_RANKING_ROW_MS) times.push(t)
  return times
}
