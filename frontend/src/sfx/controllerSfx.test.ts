// コントローラ効果音導出+エンジンの発火ログのテスト

import { describe, expect, it } from 'vitest'
import { deriveControllerSfx } from './controllerSfx'
import { SfxEngine, successNoteCount } from './engine'

describe('deriveControllerSfx', () => {
  it('flash 受信で pad_flash(演出と同時。ws-messages.md §4)', () => {
    expect(deriveControllerSfx({ type: 'flash', payload: { result: 'scored' } })).toEqual([
      'pad_flash',
    ])
  })

  it('sfx 明示送信は無条件で再生', () => {
    expect(deriveControllerSfx({ type: 'sfx', payload: { id: 'pad_button' } })).toEqual([
      'pad_button',
    ])
  })

  it('snapshot / input_mode / lang は無音', () => {
    expect(
      deriveControllerSfx({
        type: 'snapshot',
        payload: { screen: 'idle_title', lang: 'ja', input_mode: 'buttons', name_text: '' },
      }),
    ).toEqual([])
    expect(
      deriveControllerSfx({ type: 'input_mode', payload: { mode: 'name', name_text: '' } }),
    ).toEqual([])
    expect(deriveControllerSfx({ type: 'lang', payload: { lang: 'en' } })).toEqual([])
  })
})

describe('SfxEngine', () => {
  it('AudioContext 未生成(アンロック前)でも発火ログには記録される', () => {
    const engine = new SfxEngine()
    engine.play('decide')
    engine.play('judge_success', { points: 12 })
    expect(engine.playedIds).toEqual(['decide', 'judge_success'])
  })

  it('successNoteCount は得点に応じて4〜8音(§5.12「得点に応じて豪華に」)', () => {
    expect(successNoteCount(0)).toBe(4)
    expect(successNoteCount(9)).toBe(4)
    expect(successNoteCount(10)).toBe(5)
    expect(successNoteCount(40)).toBe(8)
    expect(successNoteCount(999)).toBe(8)
  })
})
