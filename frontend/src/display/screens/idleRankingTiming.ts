// 待機ランキングのせり上がり時間。サーバーのタイマー
// (server/app/state/machine.py の IDLE_RANKING_*)と同じ式・同値に保ち、
// 演出の終了とサーバーのタイムアウトを一致させる。

export const IDLE_RANKING_ROW_MS = 1_000
const SCROLL_MIN_MS = 2_000
const SCROLL_MAX_MS = 27_000

export function idleRankingScrollMs(rows: number): number {
  return Math.min(Math.max(rows * IDLE_RANKING_ROW_MS, SCROLL_MIN_MS), SCROLL_MAX_MS)
}
