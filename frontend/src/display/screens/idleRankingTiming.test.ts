// 待機ランキングのせり上がり時間と効果音タイミングのテスト
// (server/app/state/machine.py の IDLE_RANKING_* と同式・同値)

import { describe, expect, it } from 'vitest'
import { idleRankingScrollMs, idleRankingTickTimes } from './idleRankingTiming'

describe('idleRankingScrollMs', () => {
  it('行数×1秒。下限2秒・上限27秒でクランプ', () => {
    expect(idleRankingScrollMs(0)).toBe(2_000)
    expect(idleRankingScrollMs(1)).toBe(2_000)
    expect(idleRankingScrollMs(5)).toBe(5_000)
    expect(idleRankingScrollMs(100)).toBe(27_000)
  })
})

describe('idleRankingTickTimes', () => {
  it('1秒ごとに刻み、終端(ファンファーレ時刻)は含まない', () => {
    expect(idleRankingTickTimes(3)).toEqual([1_000, 2_000])
    expect(idleRankingTickTimes(1)).toEqual([1_000])
  })

  it('上限クランプ時も終端手前まで(最大26ティック)', () => {
    const times = idleRankingTickTimes(100)
    expect(times).toHaveLength(26)
    expect(times[times.length - 1]).toBe(26_000)
  })
})
