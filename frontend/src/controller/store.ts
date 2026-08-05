// iPadコントローラの受信状態(純リデューサ)。仕様§6: iPadは状態を持たず、
// 入力モード・言語はすべてサーバー配信(snapshot / input_mode / lang)に従う。
// 名前入力欄のローカル編集のみクライアント側アクション(type_name)で扱う
// (サーバーは name_text をコントローラへエコーしないため)。

import type { ControllerInputMode, ControllerMessage, Lang, ScreenId } from '../contracts/ws'

export type FlashKind = 'scored' | 'failed' | 'duplicate'

export interface ControllerState {
  /** null = snapshot 受信前 */
  screen: ScreenId | null
  lang: Lang
  inputMode: ControllerInputMode
  nameText: string
  /** 判定フラッシュ演出。count で連続判定でも再トリガーする */
  flash: { result: FlashKind; count: number } | null
}

export const initialControllerState: ControllerState = {
  screen: null,
  lang: 'ja',
  inputMode: 'buttons',
  nameText: '',
  flash: null,
}

export type ControllerAction = ControllerMessage | { type: 'type_name'; text: string }

export const NAME_MAX_CHARS = 10

/** 名前入力の切り詰め(ws-messages.md §6: クライアントで10文字に切り詰めて送る) */
export function clampName(text: string): string {
  return [...text].slice(0, NAME_MAX_CHARS).join('')
}

/**
 * 再接続 snapshot に対して、切断中にローカル編集した名前を復元・再送すべきなら
 * その値を返す(null = 復元不要)。send() は未接続時に破棄するため、切断中の
 * 入力はサーバーに届いておらず、snapshot の古い name_text に上書きされてしまう。
 * lastTyped はユーザーが最後に入力した値(input_mode 受信でリセットする)。
 */
export function nameToRestore(msg: ControllerMessage, lastTyped: string | null): string | null {
  if (msg.type !== 'snapshot' || lastTyped === null) return null
  if (msg.payload.input_mode !== 'name') return null
  const clamped = clampName(lastTyped)
  return clamped !== msg.payload.name_text ? clamped : null
}

export function reduceController(
  state: ControllerState,
  action: ControllerAction,
): ControllerState {
  switch (action.type) {
    case 'snapshot': {
      const { screen, lang, input_mode, name_text } = action.payload
      // flash は瞬間演出のため snapshot では復元しない
      return { screen, lang, inputMode: input_mode, nameText: name_text, flash: null }
    }
    case 'input_mode':
      return { ...state, inputMode: action.payload.mode, nameText: action.payload.name_text }
    case 'lang':
      return { ...state, lang: action.payload.lang }
    case 'flash':
      return {
        ...state,
        flash: { result: action.payload.result, count: (state.flash?.count ?? 0) + 1 },
      }
    case 'type_name':
      return { ...state, nameText: clampName(action.text) }
    default:
      // sfx(S6で対応)・未知の type は無視(契約)
      return state
  }
}
