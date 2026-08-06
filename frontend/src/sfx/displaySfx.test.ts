// ディスプレイ効果音導出のテスト(ws-messages.md §4 の発火表)

import { describe, expect, it } from 'vitest'
import type { DisplayMessage, Judge, ScreenState } from '../contracts/ws'
import type { DisplayState } from '../display/store'
import { deriveDisplaySfx } from './displaySfx'

function stateOf(screen: ScreenState | null): DisplayState {
  return { screen, lang: 'ja', board: null, lastJudge: null, cameraSide: 'back' }
}

function screenMsg(payload: ScreenState): DisplayMessage {
  return { type: 'screen', payload }
}

const MODE_SELECT: ScreenState = { screen: 'mode_select', ctx: { focus: 'rules' } }
const PRACTICE: ScreenState = { screen: 'practice', ctx: { score: 0, selection: null } }
const GAME_PLAY: ScreenState = {
  screen: 'game_play',
  ctx: { score: 0, fail_count: 0, remaining_ms: 60_000 },
}
const RESULT: ScreenState = {
  screen: 'result',
  ctx: {
    score: 10,
    fail_count: 0,
    rank: 1,
    name_text: '',
    focus: 'decide',
    input_mode: 'name',
  },
}

function judgeOf(result: Judge['result'], points = 0): DisplayMessage {
  return {
    type: 'judge',
    payload: {
      seq: 1,
      result,
      points,
      min_moves: points > 0 ? 1 : null,
      board: 'L//',
      total_score: points,
      fail_count: result === 'unclearable' ? 1 : 0,
    },
  }
}

describe('deriveDisplaySfx: 画面遷移', () => {
  it('前進遷移は decide(タイトル→モード選択、リザルト→ランキング→QR→タイトル)', () => {
    expect(
      deriveDisplaySfx(stateOf({ screen: 'idle_title', ctx: {} }), screenMsg(MODE_SELECT)),
    ).toEqual([{ id: 'decide' }])
    expect(
      deriveDisplaySfx(
        stateOf(RESULT),
        screenMsg({ screen: 'ranking', ctx: { entries: [], highlight_play_id: null } }),
      ),
    ).toEqual([{ id: 'decide' }])
    expect(
      deriveDisplaySfx(
        stateOf({ screen: 'qr', ctx: { url: 'https://x', play_id: 'p' } }),
        screenMsg({ screen: 'idle_title', ctx: {} }),
      ),
    ).toEqual([{ id: 'decide' }])
  })

  it('後退遷移は back(練習→モード選択、ダイアログ→呼び出し元)', () => {
    expect(deriveDisplaySfx(stateOf(PRACTICE), screenMsg(MODE_SELECT))).toEqual([{ id: 'back' }])
    expect(
      deriveDisplaySfx(
        stateOf({ screen: 'rule_dialog', ctx: { from: 'practice', page: 0, page_count: 5 } }),
        screenMsg(PRACTICE),
      ),
    ).toEqual([{ id: 'back' }])
  })

  it('count / go / timeup が代替する遷移は無音', () => {
    expect(
      deriveDisplaySfx(
        stateOf(MODE_SELECT),
        screenMsg({ screen: 'game_countdown', ctx: { value: '3' } }),
      ),
    ).toEqual([])
    expect(
      deriveDisplaySfx(
        stateOf({ screen: 'game_countdown', ctx: { value: 'go' } }),
        screenMsg(GAME_PLAY),
      ),
    ).toEqual([])
    expect(deriveDisplaySfx(stateOf(GAME_PLAY), screenMsg(RESULT))).toEqual([])
  })

  it('待機2画面の相互遷移(タイムアウトと区別不能)と snapshot 前は無音', () => {
    expect(
      deriveDisplaySfx(
        stateOf({ screen: 'idle_ranking', ctx: { entries: [] } }),
        screenMsg({ screen: 'idle_title', ctx: {} }),
      ),
    ).toEqual([])
    expect(deriveDisplaySfx(stateOf(null), screenMsg(MODE_SELECT))).toEqual([])
  })
})

describe('deriveDisplaySfx: 同一画面の ctx 変化', () => {
  it('mode_select の focus 移動は cursor、同値は無音', () => {
    const moved = screenMsg({ screen: 'mode_select', ctx: { focus: 'practice' } })
    expect(deriveDisplaySfx(stateOf(MODE_SELECT), moved)).toEqual([{ id: 'cursor' }])
    expect(deriveDisplaySfx(stateOf(MODE_SELECT), screenMsg(MODE_SELECT))).toEqual([])
  })

  it('rule_dialog のページ移動は cursor', () => {
    const prev = stateOf({
      screen: 'rule_dialog',
      ctx: { from: 'mode_select', page: 0, page_count: 5 },
    })
    expect(
      deriveDisplaySfx(
        prev,
        screenMsg({ screen: 'rule_dialog', ctx: { from: 'mode_select', page: 1, page_count: 5 } }),
      ),
    ).toEqual([{ id: 'cursor' }])
  })

  it('practice の選択有効化は cursor、box_moved による解除(null)は無音', () => {
    expect(
      deriveDisplaySfx(
        stateOf(PRACTICE),
        screenMsg({ screen: 'practice', ctx: { score: 0, selection: 'back' } }),
      ),
    ).toEqual([{ id: 'cursor' }])
    expect(
      deriveDisplaySfx(
        stateOf({ screen: 'practice', ctx: { score: 0, selection: 'back' } }),
        screenMsg(PRACTICE),
      ),
    ).toEqual([])
  })

  it('result の input_mode 切替は decide、focus 移動は cursor', () => {
    expect(
      deriveDisplaySfx(
        stateOf(RESULT),
        screenMsg({ screen: 'result', ctx: { ...RESULT.ctx, input_mode: 'buttons' } }),
      ),
    ).toEqual([{ id: 'decide' }])
    const buttons: ScreenState = {
      screen: 'result',
      ctx: { ...RESULT.ctx, input_mode: 'buttons' },
    }
    expect(
      deriveDisplaySfx(
        stateOf(buttons),
        screenMsg({ screen: 'result', ctx: { ...buttons.ctx, focus: 'input' } }),
      ),
    ).toEqual([{ id: 'cursor' }])
  })
})

describe('deriveDisplaySfx: countdown / timer / judge / name / lang / sfx', () => {
  it('countdown 3/2/1 は count、go は go(game_countdown 中のみ)', () => {
    const counting = stateOf({ screen: 'game_countdown', ctx: { value: '3' } })
    expect(deriveDisplaySfx(counting, { type: 'countdown', payload: { value: '3' } })).toEqual([
      { id: 'count' },
    ])
    expect(deriveDisplaySfx(counting, { type: 'countdown', payload: { value: 'go' } })).toEqual([
      { id: 'go' },
    ])
    expect(
      deriveDisplaySfx(stateOf(GAME_PLAY), { type: 'countdown', payload: { value: 'go' } }),
    ).toEqual([])
  })

  it('timer は残り10秒未満で tick10、0以下で timeup(game_play 中のみ)', () => {
    const playing = stateOf(GAME_PLAY)
    expect(deriveDisplaySfx(playing, { type: 'timer', payload: { remaining_ms: 60_000 } })).toEqual(
      [],
    )
    expect(deriveDisplaySfx(playing, { type: 'timer', payload: { remaining_ms: 10_000 } })).toEqual(
      [],
    )
    expect(deriveDisplaySfx(playing, { type: 'timer', payload: { remaining_ms: 9_000 } })).toEqual([
      { id: 'tick10' },
    ])
    expect(deriveDisplaySfx(playing, { type: 'timer', payload: { remaining_ms: 0 } })).toEqual([
      { id: 'timeup' },
    ])
    expect(
      deriveDisplaySfx(stateOf(RESULT), { type: 'timer', payload: { remaining_ms: 0 } }),
    ).toEqual([])
  })

  it('judge は結果別の3音(practice / game_play 中のみ)。scored は points 付き', () => {
    expect(deriveDisplaySfx(stateOf(PRACTICE), judgeOf('scored', 12))).toEqual([
      { id: 'judge_success', points: 12 },
    ])
    expect(deriveDisplaySfx(stateOf(GAME_PLAY), judgeOf('unclearable'))).toEqual([
      { id: 'judge_fail' },
    ])
    expect(deriveDisplaySfx(stateOf(GAME_PLAY), judgeOf('duplicate_same'))).toEqual([
      { id: 'judge_dup' },
    ])
    expect(deriveDisplaySfx(stateOf(GAME_PLAY), judgeOf('duplicate_mirror'))).toEqual([
      { id: 'judge_dup' },
    ])
    expect(deriveDisplaySfx(stateOf(MODE_SELECT), judgeOf('scored', 1))).toEqual([])
  })

  it('name はミラー文字列の変化時のみ key_touch', () => {
    expect(deriveDisplaySfx(stateOf(RESULT), { type: 'name', payload: { text: 'あ' } })).toEqual([
      { id: 'key_touch' },
    ])
    expect(deriveDisplaySfx(stateOf(RESULT), { type: 'name', payload: { text: '' } })).toEqual([])
    expect(
      deriveDisplaySfx(stateOf(MODE_SELECT), { type: 'name', payload: { text: 'あ' } }),
    ).toEqual([])
  })

  it('lang は mode_select 中(言語トグル)のみ cursor。待機リセットは無音', () => {
    expect(
      deriveDisplaySfx(stateOf(MODE_SELECT), { type: 'lang', payload: { lang: 'en' } }),
    ).toEqual([{ id: 'cursor' }])
    expect(
      deriveDisplaySfx(stateOf({ screen: 'qr', ctx: { url: 'u', play_id: 'p' } }), {
        type: 'lang',
        payload: { lang: 'ja' },
      }),
    ).toEqual([])
  })

  it('サーバーの sfx 明示送信は無条件で再生、snapshot は無音', () => {
    expect(
      deriveDisplaySfx(stateOf(MODE_SELECT), { type: 'sfx', payload: { id: 'fanfare' } }),
    ).toEqual([{ id: 'fanfare' }])
    expect(
      deriveDisplaySfx(stateOf(null), {
        type: 'snapshot',
        payload: { screen: 'idle_title', ctx: {}, lang: 'ja', board: null, camera_side: 'back' },
      }),
    ).toEqual([])
  })
})
