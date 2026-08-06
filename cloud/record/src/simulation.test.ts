// シミュレーション再生のテスト。実物の precompute.json(同梱テーブル)で
// min_path を初期個体に適用し、最終盤面が鏡像に一致することまで検証する。

import { describe, expect, it } from 'vitest'
import { boxCount, mirrorBoard, parseBoard } from './contracts/board'
import { precomputeFor } from './contracts/precompute'
import { towerTuple, type TowerBoxIds } from './contracts/play'
import { demoPlay } from './demo'
import { applyMove, boxSerial, boxSize, sizeTowers, stacksAfter } from './simulation'

describe('boxSize / boxSerial', () => {
  it('箱IDからサイズと個体番号を取り出す', () => {
    expect(boxSize('large-1')).toBe('L')
    expect(boxSize('medium-3')).toBe('M')
    expect(boxSize('small-2')).toBe('S')
    expect(boxSerial('large-2')).toBe('2')
    expect(() => boxSize('huge-1')).toThrow()
  })
})

describe('applyMove', () => {
  const stacks: TowerBoxIds = [['large-1'], ['medium-1', 'small-1'], []]

  it('from塔の最上段を to塔へ動かす(元の配列は不変)', () => {
    const { stacks: next, movedBoxId } = applyMove(stacks, { size: 'S', from: 'B', to: 'C' })
    expect(movedBoxId).toBe('small-1')
    expect(next).toEqual([['large-1'], ['medium-1'], ['small-1']])
    expect(stacks[1]).toEqual(['medium-1', 'small-1'])
  })

  it('最上段のサイズが合わない・空塔からの移動は例外', () => {
    expect(() => applyMove(stacks, { size: 'M', from: 'B', to: 'C' })).toThrow()
    expect(() => applyMove(stacks, { size: 'L', from: 'C', to: 'A' })).toThrow()
  })
})

describe('min_path の適用(仕様§5.10 のシミュレーション再生)', () => {
  // 判定履歴の tower_box_ids を初期状態に、事前計算の最短手順を最後まで適用すると
  // クリア条件1(サイズまで含めた左右反転、S11)の盤面に到達する
  it.each([
    { board: 'L/MS/L', initial: [['large-1'], ['medium-1', 'small-1'], ['large-2']] },
    { board: 'LMS//', initial: [['large-1', 'medium-1', 'small-1'], [], []] },
    {
      board: 'LMS/LM/LMS',
      initial: [
        ['large-1', 'medium-1', 'small-1'],
        ['large-2', 'medium-2'],
        ['large-3', 'medium-3', 'small-2'],
      ],
    },
  ])('$board の最短手順で鏡像に到達する', ({ board, initial }) => {
    const entry = precomputeFor(board)
    expect(entry.clearable).toBe(true)
    const path = entry.min_path
    if (path === null) throw new Error('unreachable')
    expect(path).toHaveLength(entry.min_moves ?? -1)

    // 途中の全手が合法(applyMove が例外を出さない)に適用でき、最終形が鏡像
    const { stacks } = stacksAfter(initial as TowerBoxIds, path, path.length)
    expect(sizeTowers(stacks)).toEqual(parseBoard(mirrorBoard(board)))

    // クリア条件2: 少なくとも1個の箱が初期とは別の塔にある(game-core-api.md §4)
    const towerOf = (target: TowerBoxIds) =>
      new Map(target.flatMap((tower, i) => tower.map((id) => [id, i] as const)))
    const before = towerOf(initial as TowerBoxIds)
    const after = towerOf(stacks)
    const moved = [...before].filter(([id, tower]) => after.get(id) !== tower)
    expect(moved.length).toBeGreaterThan(0)
  })
})

describe('デモデータの整合(demo.ts)', () => {
  it('盤面文字列と個体列のサイズが一致し、結果が事前計算と整合する', () => {
    for (const j of demoPlay.judgements) {
      expect(sizeTowers(towerTuple(j.tower_box_ids))).toEqual(parseBoard(j.board))
      const entry = precomputeFor(j.board)
      if (j.result === 'unclearable') {
        expect(entry.clearable).toBe(false)
      } else {
        expect(entry.clearable).toBe(true)
        expect(j.min_moves).toBe(entry.min_moves)
      }
      if (j.result === 'scored') {
        expect(j.points).toBe(boxCount(j.board) * (entry.min_moves ?? 0))
      }
    }
    expect(demoPlay.score).toBe(demoPlay.judgements.reduce((sum, j) => sum + j.points, 0))
    expect(demoPlay.fail_count).toBe(
      demoPlay.judgements.filter((j) => j.result === 'unclearable').length,
    )
  })
})
