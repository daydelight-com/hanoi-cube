import { describe, expect, it } from 'vitest'
import type { DisplayMessage } from '../contracts/ws'
import { initialDisplayState, reduceDisplay } from './store'

const snapshot: DisplayMessage = {
  type: 'snapshot',
  payload: {
    screen: 'game_play',
    ctx: { score: 12, fail_count: 1, remaining_ms: 43000 },
    lang: 'en',
    board: {
      t_ms: 100,
      towers: ['LMS', '', 'L'],
      board: 'LMS//L',
      legal: true,
      violations: [],
      staging_box_ids: ['medium-2', 'small-3'],
    },
  },
}

describe('reduceDisplay', () => {
  it('snapshot で screen / lang / board を一括上書きする', () => {
    const s = reduceDisplay(initialDisplayState, snapshot)
    expect(s.screen).toEqual({
      screen: 'game_play',
      ctx: { score: 12, fail_count: 1, remaining_ms: 43000 },
    })
    expect(s.lang).toBe('en')
    expect(s.board?.board).toBe('LMS//L')
  })

  it('screen / lang / board を個別に更新する', () => {
    let s = reduceDisplay(initialDisplayState, snapshot)
    s = reduceDisplay(s, { type: 'screen', payload: { screen: 'idle_title', ctx: {} } })
    expect(s.screen?.screen).toBe('idle_title')
    expect(s.board?.board).toBe('LMS//L') // 盤面は保持

    s = reduceDisplay(s, { type: 'lang', payload: { lang: 'ja' } })
    expect(s.lang).toBe('ja')

    s = reduceDisplay(s, {
      type: 'board',
      payload: {
        t_ms: 200,
        towers: ['', 'S', 'L'],
        board: '/S/L',
        legal: true,
        violations: [],
        staging_box_ids: [],
      },
    })
    expect(s.board?.board).toBe('/S/L')
  })

  it('snapshot 前でも screen 単独受信で描画状態になる', () => {
    const s = reduceDisplay(initialDisplayState, {
      type: 'screen',
      payload: { screen: 'idle_title', ctx: {} },
    })
    expect(s.screen?.screen).toBe('idle_title')
  })

  it('未対応 type(judge等)と未知 type は状態を変えない', () => {
    const s = reduceDisplay(initialDisplayState, snapshot)
    const judged = reduceDisplay(s, {
      type: 'judge',
      payload: {
        seq: 1,
        result: 'scored',
        points: 12,
        min_moves: 3,
        board: 'LMS//L',
        total_score: 12,
        fail_count: 0,
      },
    })
    expect(judged).toBe(s)
    const unknown = reduceDisplay(s, { type: 'nonsense' } as unknown as DisplayMessage)
    expect(unknown).toBe(s)
  })
})
