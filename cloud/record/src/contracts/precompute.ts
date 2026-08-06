// 事前計算テーブル(契約: docs/contracts/game-core-api.md §3)。
// server/app/core/data/precompute.json をビルド時に同梱する(firestore.md §1)。
// 記録画面はこのテーブルから board で最短手順を引いてシミュレーション再生する。

import { boardIndex, type SizeChar, type TowerName } from './board'
import raw from '../../../../server/app/core/data/precompute.json'

export interface Move {
  size: SizeChar
  from: TowerName
  to: TowerName
}

export interface PrecomputeEntry {
  board: string
  index: number
  clearable: boolean
  min_moves: number | null
  min_path: Move[] | null
  mirror: string
  canonical_key: string
}

interface PrecomputeTable {
  version: number
  boards: PrecomputeEntry[]
}

const table = raw as unknown as PrecomputeTable

/** 盤面文字列から事前計算エントリを引く(配列添字 = board_index)。不正盤面は例外 */
export function precomputeFor(board: string): PrecomputeEntry {
  const entry = table.boards[boardIndex(board)]
  if (entry.board !== board) throw new Error(`precompute table mismatch for ${board}`)
  return entry
}
