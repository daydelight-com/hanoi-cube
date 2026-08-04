// 盤面表現のTS写し(契約: docs/contracts/board.md)のテスト。
// server/tests/test_board.py と同内容を検証し、Python/TS間のドリフトを検出する。

import { describe, expect, it } from 'vitest'
import {
  TOWER_STATES,
  boardFromIndex,
  boardIndex,
  boxCount,
  canonicalKey,
  formatBoard,
  isLegalBoard,
  isLegalTower,
  mirrorBoard,
  parseBoard,
} from './board'

describe('board contract (board.md)', () => {
  it('塔状態は合法8通り(ルールブック§3の並び順)', () => {
    expect(TOWER_STATES).toEqual(['', 'S', 'M', 'L', 'MS', 'LS', 'LM', 'LMS'])
    for (const t of TOWER_STATES) expect(isLegalTower(t)).toBe(true)
    expect(isLegalTower('SL')).toBe(false)
    expect(isLegalTower('LL')).toBe(false)
    expect(isLegalTower('LMSS')).toBe(false)
  })

  it('parse / format の往復', () => {
    expect(parseBoard('LMS//L')).toEqual(['LMS', '', 'L'])
    expect(formatBoard(['LMS', '', 'L'])).toBe('LMS//L')
    expect(parseBoard('//')).toEqual(['', '', ''])
  })

  it.each(['', 'LMS/L', 'LMS//L/', 'lms//L', 'LMS/-/L', 'LMX//L', 'LMS//L\n', ' LMS//L'])(
    '形式不正を拒否する: %j',
    (bad) => {
      expect(() => parseBoard(bad)).toThrow()
      expect(isLegalBoard(bad)).toBe(false)
    },
  )

  it('鏡像と正準キー', () => {
    expect(mirrorBoard('LMS//L')).toBe('L//LMS')
    expect(mirrorBoard('L//LMS')).toBe('LMS//L')
    expect(canonicalKey('LMS//L')).toBe('L//LMS')
    expect(canonicalKey('L//LMS')).toBe('L//LMS')
    expect(canonicalKey('L/MS/L')).toBe('L/MS/L') // 左右対称は自分自身
    expect(canonicalKey('LMS//')).toBe(canonicalKey('//LMS')) // ルールブック§6
  })

  it('盤面インデックス 0〜511 の往復', () => {
    const seen = new Set<string>()
    for (let index = 0; index < 512; index++) {
      const board = boardFromIndex(index)
      expect(boardIndex(board)).toBe(index)
      expect(isLegalBoard(board)).toBe(true)
      seen.add(board)
    }
    expect(seen.size).toBe(512)
    expect(() => boardFromIndex(512)).toThrow()
    expect(() => boardIndex('SL//')).toThrow() // 形式は正しいが不正盤面
  })

  it('boxCount(得点の係数)', () => {
    expect(boxCount('//')).toBe(0)
    expect(boxCount('LMS//L')).toBe(4)
    expect(boxCount('LMS/LMS/LMS')).toBe(9)
  })
})
