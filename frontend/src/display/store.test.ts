import { describe, expect, it } from 'vitest'
import type { DisplayMessage } from '../contracts/ws'
import { initialDisplayState, reduceDisplay, type DisplayState } from './store'

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
      tower_box_ids: [['large-1', 'medium-1', 'small-1'], [], ['large-2']],
    },
  },
}

const judgeMsg: DisplayMessage = {
  type: 'judge',
  payload: {
    seq: 2,
    result: 'scored',
    points: 9,
    min_moves: 3,
    board: 'LMS//L',
    total_score: 21,
    fail_count: 1,
  },
}

function at(screen: DisplayState['screen']): DisplayState {
  return { ...initialDisplayState, screen }
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
        tower_box_ids: [[], ['small-1'], ['large-1']],
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

  it('countdown は game_countdown の ctx.value を更新する', () => {
    const base = at({ screen: 'game_countdown', ctx: { value: '3' } })
    const s = reduceDisplay(base, { type: 'countdown', payload: { value: 'go' } })
    expect(s.screen).toEqual({ screen: 'game_countdown', ctx: { value: 'go' } })
    // 画面が違えば無視(遷移直後の追い越しフレーム)
    const other = at({ screen: 'idle_title', ctx: {} })
    expect(reduceDisplay(other, { type: 'countdown', payload: { value: '2' } })).toBe(other)
  })

  it('timer は game_play の remaining_ms のみ更新する', () => {
    const base = reduceDisplay(initialDisplayState, snapshot)
    const s = reduceDisplay(base, { type: 'timer', payload: { remaining_ms: 9000 } })
    expect(s.screen).toEqual({
      screen: 'game_play',
      ctx: { score: 12, fail_count: 1, remaining_ms: 9000 },
    })
    const other = at({ screen: 'idle_title', ctx: {} })
    expect(reduceDisplay(other, { type: 'timer', payload: { remaining_ms: 9000 } })).toBe(other)
  })

  it('judge は game_play のスコア・失敗数と lastJudge を更新する', () => {
    const base = reduceDisplay(initialDisplayState, snapshot)
    const s = reduceDisplay(base, judgeMsg)
    expect(s.screen).toEqual({
      screen: 'game_play',
      ctx: { score: 21, fail_count: 1, remaining_ms: 43000 },
    })
    expect(s.lastJudge?.seq).toBe(2)
  })

  it('screen で画面が変わると lastJudge を捨てる(演出の持ち越し防止)', () => {
    const base = reduceDisplay(reduceDisplay(initialDisplayState, snapshot), judgeMsg)
    expect(base.lastJudge).not.toBeNull()
    // 同一画面の screen(判定と同時に届く)では保持する
    const same = reduceDisplay(base, {
      type: 'screen',
      payload: { screen: 'game_play', ctx: { score: 21, fail_count: 1, remaining_ms: 43000 } },
    })
    expect(same.lastJudge?.seq).toBe(2)
    // 別画面への遷移で捨てる
    const moved = reduceDisplay(same, {
      type: 'screen',
      payload: {
        screen: 'result',
        ctx: {
          score: 21,
          fail_count: 1,
          rank: 1,
          name_text: '',
          focus: 'decide',
          input_mode: 'name',
        },
      },
    })
    expect(moved.lastJudge).toBeNull()
  })

  it('judge は practice ではスコアのみ ctx に反映する', () => {
    const base = at({ screen: 'practice', ctx: { score: 12, selection: null } })
    const s = reduceDisplay(base, judgeMsg)
    expect(s.screen).toEqual({ screen: 'practice', ctx: { score: 21, selection: null } })
    // 判定できない画面では無視
    const other = at({ screen: 'idle_title', ctx: {} })
    expect(reduceDisplay(other, judgeMsg)).toBe(other)
  })

  it('name は result の name_text をミラーする', () => {
    const base = at({
      screen: 'result',
      ctx: {
        score: 30,
        fail_count: 0,
        rank: 1,
        name_text: '',
        focus: 'decide',
        input_mode: 'name',
      },
    })
    const s = reduceDisplay(base, { type: 'name', payload: { text: 'たろう' } })
    expect(s.screen?.ctx).toMatchObject({ name_text: 'たろう' })
    const other = at({ screen: 'idle_title', ctx: {} })
    expect(reduceDisplay(other, { type: 'name', payload: { text: 'x' } })).toBe(other)
  })

  it('ranking は idle_ranking / ranking の entries を更新する', () => {
    const entry = {
      rank: 1,
      name: 'たろう',
      score: 120,
      fail_count: 2,
      play_id: 'p1',
      played_at: '2026-08-21T10:00:00+09:00',
    }
    const idle = at({ screen: 'idle_ranking', ctx: { entries: [] } })
    const s1 = reduceDisplay(idle, {
      type: 'ranking',
      payload: { entries: [entry], highlight_play_id: null },
    })
    expect(s1.screen).toEqual({ screen: 'idle_ranking', ctx: { entries: [entry] } })

    const rank = at({ screen: 'ranking', ctx: { entries: [], highlight_play_id: null } })
    const s2 = reduceDisplay(rank, {
      type: 'ranking',
      payload: { entries: [entry], highlight_play_id: 'p1' },
    })
    expect(s2.screen).toEqual({
      screen: 'ranking',
      ctx: { entries: [entry], highlight_play_id: 'p1' },
    })

    const other = at({ screen: 'idle_title', ctx: {} })
    expect(
      reduceDisplay(other, { type: 'ranking', payload: { entries: [], highlight_play_id: null } }),
    ).toBe(other)
  })

  it('snapshot は lastJudge をリセットする(再接続時の古い演出防止)', () => {
    const withJudge = reduceDisplay(reduceDisplay(initialDisplayState, snapshot), judgeMsg)
    expect(withJudge.lastJudge).not.toBeNull()
    expect(reduceDisplay(withJudge, snapshot).lastJudge).toBeNull()
  })

  it('未知 type は状態を変えない', () => {
    const s = reduceDisplay(initialDisplayState, snapshot)
    const unknown = reduceDisplay(s, { type: 'nonsense' } as unknown as DisplayMessage)
    expect(unknown).toBe(s)
  })
})
