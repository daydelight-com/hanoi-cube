// 待機ランキングのせり上がり時間のテスト
// (server/app/state/machine.py の IDLE_RANKING_* と同式・同値)

import { describe, expect, it } from 'vitest'
import { idleRankingScrollMs } from './idleRankingTiming'

describe('idleRankingScrollMs', () => {
  it('行数×1秒。下限2秒・上限27秒でクランプ', () => {
    expect(idleRankingScrollMs(0)).toBe(2_000)
    expect(idleRankingScrollMs(1)).toBe(2_000)
    expect(idleRankingScrollMs(5)).toBe(5_000)
    expect(idleRankingScrollMs(100)).toBe(27_000)
  })
})
