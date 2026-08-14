import { describe, expect, it } from 'vitest'
import { faceImageUrl, tagRect } from './textures'

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

describe('faceImageUrl', () => {
  it('大・中の面1と面6はロゴ入りアート', () => {
    expect(faceImageUrl('large', 1)).toBe('/textures/cube_l_logo.png')
    expect(faceImageUrl('large', 6)).toBe('/textures/cube_l_logo.png')
    expect(faceImageUrl('medium', 1)).toBe('/textures/cube_m_logo.png')
  })

  it('面2〜5はロゴなしアート', () => {
    for (const face of [2, 3, 4, 5]) {
      expect(faceImageUrl('large', face)).toBe('/textures/cube_l.png')
      expect(faceImageUrl('medium', face)).toBe('/textures/cube_m.png')
    }
  })

  it('小箱はロゴなし素材のみのため全面共通', () => {
    for (const face of [1, 2, 3, 4, 5, 6]) {
      expect(faceImageUrl('small', face)).toBe('/textures/cube_s.png')
    }
  })
})
