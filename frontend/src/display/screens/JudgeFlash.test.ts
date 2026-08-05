import { describe, expect, it } from 'vitest'
import type { Judge } from '../../contracts/ws'
import { judgeFlashView } from './judgeView'

function judgeOf(result: Judge['result'], points = 0): Judge {
  return {
    seq: 1,
    result,
    points,
    min_moves: result === 'unclearable' ? null : 3,
    board: 'LMS//L',
    total_score: points,
    fail_count: result === 'unclearable' ? 1 : 0,
  }
}

describe('judgeFlashView', () => {
  it('scored は +N(言語非依存。§5.13)', () => {
    expect(judgeFlashView(judgeOf('scored', 12), 'ja')).toEqual({ kind: 'scored', text: '+12' })
    expect(judgeFlashView(judgeOf('scored', 12), 'en')).toEqual({ kind: 'scored', text: '+12' })
  })

  it('unclearable は失敗演出(言語別)', () => {
    expect(judgeFlashView(judgeOf('unclearable'), 'ja')).toEqual({
      kind: 'failed',
      text: 'しっぱい...',
    })
    expect(judgeFlashView(judgeOf('unclearable'), 'en').kind).toBe('failed')
  })

  it('duplicate_same / duplicate_mirror は「判定済み」表示(§5.6)', () => {
    expect(judgeFlashView(judgeOf('duplicate_same'), 'ja')).toEqual({
      kind: 'duplicate',
      text: 'はんていずみ',
    })
    expect(judgeFlashView(judgeOf('duplicate_mirror'), 'en').kind).toBe('duplicate')
  })
})
