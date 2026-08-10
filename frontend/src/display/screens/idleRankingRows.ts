// 待機ランキングの表示データ整形。仕様§5.2の演出でも表の並びは常に「上位が上」とする。

import type { RankingEntry } from '../../contracts/ws'

/** 待機ランキングの表示順(1位が先頭)。同順位はサーバーの並びを保つ */
export function idleRankingRows(entries: RankingEntry[]): RankingEntry[] {
  return [...entries].sort((a, b) => a.rank - b.rank)
}
