import { describe, expect, it } from 'vitest'
import type { BoxObservation } from '../contracts/cv'
import {
  GROUND_OFFSET_GAIN,
  GROUND_OFFSET_MAX_MM,
  measuredGroundErrorMm,
  nextGroundOffsetMm,
} from './groundOffset'

function box(over: Partial<BoxObservation>): BoxObservation {
  return {
    box_id: 'large-1',
    size: 'large',
    pos_mm: [210, 208, 0],
    quat: [0, 0, 0, 1],
    area: 'B',
    level: 0,
    visible: true,
    seen_tag_ids: [0],
    ...over,
  }
}

describe('measuredGroundErrorMm', () => {
  it('可視かつ level=0 の箱の底面zを平均する', () => {
    const boxes = [
      box({ box_id: 'large-1', pos_mm: [105, 208, -12] }),
      box({ box_id: 'large-2', pos_mm: [315, 208, -14] }),
    ]
    expect(measuredGroundErrorMm(boxes)).toBeCloseTo(-13)
  })

  it('接地箱がなければ null(空・非可視・level=null/1 は対象外)', () => {
    expect(measuredGroundErrorMm([])).toBeNull()
    expect(measuredGroundErrorMm([box({ visible: false, pos_mm: [210, 208, -12] })])).toBeNull()
    expect(measuredGroundErrorMm([box({ level: null, area: null })])).toBeNull()
    expect(measuredGroundErrorMm([box({ level: 1, pos_mm: [210, 208, 63] })])).toBeNull()
  })
})

describe('nextGroundOffsetMm', () => {
  it('接地箱が見えない間は現在値を保持する', () => {
    expect(nextGroundOffsetMm(7.5, [])).toBe(7.5)
    expect(nextGroundOffsetMm(7.5, [box({ level: 1 })])).toBe(7.5)
  })

  it('沈み(z<0)には正の補正、浮き(z>0)には負の補正へ追従する', () => {
    const sunk = [box({ pos_mm: [210, 208, -12.5] })]
    const step = nextGroundOffsetMm(0, sunk)
    expect(step).toBeCloseTo(12.5 * GROUND_OFFSET_GAIN)
    const floating = [box({ pos_mm: [210, 208, 10] })]
    expect(nextGroundOffsetMm(0, floating)).toBeCloseTo(-10 * GROUND_OFFSET_GAIN)
  })

  it('反復適用で誤差を打ち消す値に収束する', () => {
    const boxes = [box({ pos_mm: [210, 208, -12.5] })]
    let offset = 0
    for (let i = 0; i < 200; i++) offset = nextGroundOffsetMm(offset, boxes)
    expect(offset).toBeCloseTo(12.5, 1)
  })

  it('補正の目標値は ±GROUND_OFFSET_MAX_MM でクランプされる', () => {
    const deepSunk = [box({ pos_mm: [210, 208, -100] })]
    let offset = 0
    for (let i = 0; i < 500; i++) offset = nextGroundOffsetMm(offset, deepSunk)
    expect(offset).toBeCloseTo(GROUND_OFFSET_MAX_MM, 1)
    const highFloat = [box({ pos_mm: [210, 208, 100] })]
    offset = 0
    for (let i = 0; i < 500; i++) offset = nextGroundOffsetMm(offset, highFloat)
    expect(offset).toBeCloseTo(-GROUND_OFFSET_MAX_MM, 1)
  })
})
