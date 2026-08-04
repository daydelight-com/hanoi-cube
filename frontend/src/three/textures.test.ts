import { describe, expect, it } from 'vitest'
import { tagRect } from './textures'

describe('tagRect', () => {
  it('大箱(75mm)の右上隅: タグ20mm+余白3mm', () => {
    const r = tagRect({ box_mm: 75, tag_mm: 20, placement: 'top_right' })
    expect(r.size).toBeCloseTo(20 / 75)
    expect(r.x).toBeCloseTo(1 - 20 / 75 - 3 / 75)
    expect(r.y).toBeCloseTo(3 / 75)
  })

  it('小箱(30mm)の中央: タグ30mmで全面', () => {
    const r = tagRect({ box_mm: 30, tag_mm: 30, placement: 'center' })
    expect(r).toEqual({ x: 0, y: 0, size: 1 })
  })

  it('タグが面より大きくてもはみ出さない(クランプ)', () => {
    const r = tagRect({ box_mm: 30, tag_mm: 40, placement: 'top_right' })
    expect(r.size).toBe(1)
    expect(r.x).toBe(0)
    expect(r.y).toBe(0)
  })
})
