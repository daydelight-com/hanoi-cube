// ディスプレイの受信状態(純リデューサ)。boxes ストリームは高頻度のため React の
// 状態には持たず、BoardScene へ直接流す(DisplayApp 参照)。ここは低頻度の
// screen / lang / board / snapshot を扱う。S4 以降の画面実装もこの状態を購読する。

import type { CvBoardUpdate } from '../contracts/cv'
import type { DisplayMessage, Lang, ScreenState } from '../contracts/ws'

export type ConfirmedBoard = Omit<CvBoardUpdate, 'kind'>

export interface DisplayState {
  /** null = snapshot 受信前 */
  screen: ScreenState | null
  lang: Lang
  /** 最新の確定盤面(未確定なら null) */
  board: ConfirmedBoard | null
}

export const initialDisplayState: DisplayState = {
  screen: null,
  lang: 'ja',
  board: null,
}

/** 受信メッセージを状態に畳み込む。未知・未対応の type は無視する(契約) */
export function reduceDisplay(state: DisplayState, msg: DisplayMessage): DisplayState {
  switch (msg.type) {
    case 'snapshot': {
      const { lang, board, ...screen } = msg.payload
      return { screen: screen as ScreenState, lang, board }
    }
    case 'screen':
      return { ...state, screen: msg.payload }
    case 'lang':
      return { ...state, lang: msg.payload.lang }
    case 'board':
      return { ...state, board: msg.payload }
    default:
      return state
  }
}
