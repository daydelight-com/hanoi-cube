// 待機ランキングのせり上がり時間のテスト
// (server/app/state/machine.py の IDLE_RANKING_* と同式・同値)

import { describe, expect, it } from 'vitest'
import { idleRankingEndY, idleRankingScrollMs } from './idleRankingTiming'

describe('idleRankingScrollMs', () => {
  it('行数×1秒。下限2秒・上限120秒でクランプ', () => {
    expect(idleRankingScrollMs(0)).toBe(2_000)
    expect(idleRankingScrollMs(1)).toBe(2_000)
    expect(idleRankingScrollMs(5)).toBe(5_000)
    expect(idleRankingScrollMs(100)).toBe(100_000)
    expect(idleRankingScrollMs(500)).toBe(120_000)
  })
})

describe('idleRankingEndY', () => {
  it('1画面に収まるなら見出し直下(0)で止まる', () => {
    expect(idleRankingEndY(400, 800)).toBe(0)
    expect(idleRankingEndY(800, 800)).toBe(0)
  })

  it('収まらないなら末尾まで流し切る位置(負値)', () => {
    expect(idleRankingEndY(1_400, 800)).toBe(-600)
  })
})
