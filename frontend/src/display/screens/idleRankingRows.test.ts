// 待機ランキングの表示順のテスト(上位が上)

import { describe, expect, it } from 'vitest'
import type { RankingEntry } from '../../contracts/ws'
import { idleRankingRows } from './idleRankingRows'

function entry(rank: number, name: string): RankingEntry {
  return {
    play_id: `p${rank}-${name}`,
    rank,
    name,
    score: 1000 - rank,
    fail_count: 0,
    played_at: '2025-08-21T10:00:00Z',
  }
}

describe('idleRankingRows', () => {
  it('1位が先頭・最下位が末尾になる', () => {
    const rows = idleRankingRows([entry(3, 'c'), entry(1, 'a'), entry(2, 'b')])
    expect(rows.map((e) => e.rank)).toEqual([1, 2, 3])
  })

  it('同順位は元の並びを保つ', () => {
    const rows = idleRankingRows([entry(1, 'a'), entry(2, 'x'), entry(2, 'y')])
    expect(rows.map((e) => e.name)).toEqual(['a', 'x', 'y'])
  })

  it('入力配列を破壊しない', () => {
    const input = [entry(2, 'b'), entry(1, 'a')]
    idleRankingRows(input)
    expect(input.map((e) => e.rank)).toEqual([2, 1])
  })
})
