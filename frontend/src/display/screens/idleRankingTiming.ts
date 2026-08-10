// 待機ランキングのせり上がり時間。サーバーのタイマー
// (server/app/state/machine.py の IDLE_RANKING_*)と同じ式・同値に保ち、
// 演出の終了とサーバーのタイムアウトを一致させる。

export const IDLE_RANKING_ROW_MS = 1_000
const SCROLL_MIN_MS = 2_000
// 100人規模でも1行あたり1秒を保てるよう上限を長めに取る(仕様§5.2の「20〜30秒」
// から変更。文字を縮小せず全件を読める速度で流すことを優先する)
const SCROLL_MAX_MS = 120_000

export function idleRankingScrollMs(rows: number): number {
  return Math.min(Math.max(rows * IDLE_RANKING_ROW_MS, SCROLL_MIN_MS), SCROLL_MAX_MS)
}

/**
 * せり上がりの終点(表コンテナの translateY, px)。
 * 1画面に収まるなら 0(見出しの直下で停止し、1位が最上段に見える)。
 * 収まらないなら負値で、末尾(最下位)まで流し切った位置になる。
 */
export function idleRankingEndY(tableHeightPx: number, availableHeightPx: number): number {
  return Math.min(0, availableHeightPx - tableHeightPx)
}
