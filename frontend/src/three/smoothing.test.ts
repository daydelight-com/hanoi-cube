import { describe, expect, it } from 'vitest'
import { dampFactor } from './smoothing'

describe('dampFactor', () => {
  it('0..1 の範囲で dt に対して単調増加', () => {
    expect(dampFactor(12, 0)).toBe(0)
    expect(dampFactor(12, 1 / 60)).toBeGreaterThan(0)
    expect(dampFactor(12, 1 / 30)).toBeGreaterThan(dampFactor(12, 1 / 60))
    expect(dampFactor(12, 10)).toBeLessThanOrEqual(1)
  })

  it('フレームレート非依存: 1/60秒×2回 と 1/30秒×1回 の収束量が一致する', () => {
    const k60 = dampFactor(12, 1 / 60)
    const k30 = dampFactor(12, 1 / 30)
    // 2回適用後の残距離 (1-k60)^2 が 1回適用の残距離 1-k30 と等しい
    expect((1 - k60) ** 2).toBeCloseTo(1 - k30, 10)
  })

  it('λ=12 は約0.2秒で9割収束する(体感チューニングの回帰テスト)', () => {
    expect(dampFactor(12, 0.2)).toBeGreaterThan(0.89)
    expect(dampFactor(12, 0.2)).toBeLessThan(0.95)
  })
})
