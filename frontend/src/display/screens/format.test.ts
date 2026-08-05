import { describe, expect, it } from 'vitest'
import { formatRemaining, isTimeCritical } from './format'

describe('formatRemaining', () => {
  it('1:00 からのカウントダウン表記(仕様§5.6)', () => {
    expect(formatRemaining(60_000)).toBe('1:00')
    expect(formatRemaining(59_000)).toBe('0:59')
    expect(formatRemaining(10_000)).toBe('0:10')
    expect(formatRemaining(1_000)).toBe('0:01')
    expect(formatRemaining(0)).toBe('0:00')
  })

  it('端数は切り上げ(残り 500ms は 0:01 と表示)', () => {
    expect(formatRemaining(500)).toBe('0:01')
    expect(formatRemaining(59_500)).toBe('1:00')
  })

  it('負値は 0:00 に丸める', () => {
    expect(formatRemaining(-1_000)).toBe('0:00')
  })
})

describe('isTimeCritical', () => {
  it('残り10秒未満で強調(§5.6: 残り10秒で強調演出)', () => {
    expect(isTimeCritical(10_000)).toBe(false)
    expect(isTimeCritical(9_999)).toBe(true)
    expect(isTimeCritical(0)).toBe(true)
  })
})
