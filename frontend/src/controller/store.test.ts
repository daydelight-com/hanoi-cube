import { describe, expect, it } from 'vitest'
import {
  clampName,
  initialControllerState,
  nameToRestore,
  reduceController,
  type ControllerState,
} from './store'

describe('reduceController', () => {
  it('snapshot で全状態を上書きする(flash は復元しない)', () => {
    const withFlash: ControllerState = {
      ...initialControllerState,
      flash: { result: 'scored', count: 3 },
    }
    const s = reduceController(withFlash, {
      type: 'snapshot',
      payload: { screen: 'result', lang: 'en', input_mode: 'name', name_text: 'たろう' },
    })
    expect(s).toEqual({
      screen: 'result',
      lang: 'en',
      inputMode: 'name',
      nameText: 'たろう',
      flash: null,
    })
  })

  it('input_mode でモードと名前フィールドの現在値を反映する(ws-messages.md §5)', () => {
    const s = reduceController(initialControllerState, {
      type: 'input_mode',
      payload: { mode: 'name', name_text: 'あい' },
    })
    expect(s.inputMode).toBe('name')
    expect(s.nameText).toBe('あい')
  })

  it('lang を切り替える', () => {
    const s = reduceController(initialControllerState, {
      type: 'lang',
      payload: { lang: 'en' },
    })
    expect(s.lang).toBe('en')
  })

  it('flash は count を増やして連続判定でも再トリガーできる', () => {
    let s = reduceController(initialControllerState, {
      type: 'flash',
      payload: { result: 'scored' },
    })
    expect(s.flash).toEqual({ result: 'scored', count: 1 })
    s = reduceController(s, { type: 'flash', payload: { result: 'failed' } })
    expect(s.flash).toEqual({ result: 'failed', count: 2 })
  })

  it('type_name は10文字に切り詰める(ws-messages.md §6)', () => {
    const s = reduceController(initialControllerState, {
      type: 'type_name',
      text: 'あいうえおかきくけこさし',
    })
    expect(s.nameText).toBe('あいうえおかきくけこ')
  })

  it('sfx 等の未対応 type は無視する(S6で対応)', () => {
    const s = reduceController(initialControllerState, {
      type: 'sfx',
      payload: { id: 'decide' },
    })
    expect(s).toBe(initialControllerState)
  })
})

describe('nameToRestore', () => {
  const snapshotOf = (input_mode: 'buttons' | 'name', name_text: string) =>
    ({
      type: 'snapshot',
      payload: { screen: 'result', lang: 'ja', input_mode, name_text },
    }) as const

  it('name モードの snapshot がローカル編集より古ければ復元値を返す', () => {
    expect(nameToRestore(snapshotOf('name', 'た'), 'たろう')).toBe('たろう')
  })

  it('snapshot と一致するなら復元不要', () => {
    expect(nameToRestore(snapshotOf('name', 'たろう'), 'たろう')).toBeNull()
  })

  it('ローカル編集がない・buttons モード・snapshot 以外は復元しない', () => {
    expect(nameToRestore(snapshotOf('name', ''), null)).toBeNull()
    expect(nameToRestore(snapshotOf('buttons', ''), 'たろう')).toBeNull()
    expect(nameToRestore({ type: 'lang', payload: { lang: 'en' } }, 'たろう')).toBeNull()
  })

  it('復元値は10文字に切り詰める', () => {
    expect(nameToRestore(snapshotOf('name', ''), 'あいうえおかきくけこさし')).toBe(
      'あいうえおかきくけこ',
    )
  })
})

describe('clampName', () => {
  it('サロゲートペアを壊さずに切り詰める', () => {
    const emoji = '😀'.repeat(12)
    expect(clampName(emoji)).toBe('😀'.repeat(10))
  })

  it('10文字以下はそのまま', () => {
    expect(clampName('たろう')).toBe('たろう')
  })
})
