// ディスプレイの受信状態(純リデューサ)。boxes ストリームは高頻度のため React の
// 状態には持たず、BoardScene へ直接流す(DisplayApp 参照)。ここは低頻度の
// screen / lang / board / snapshot と、画面内更新(countdown / timer / judge /
// name / ranking)を扱う。画面内更新は現在画面の ctx に畳み込む(screens.md §5 の
// ctx 型が表示データの単一の正)。画面が一致しない場合は無視する(遷移直後の
// 追い越しフレーム対策)。

import type { CvBoardUpdate } from '../contracts/cv'
import type { DisplayMessage, Judge, Lang, ScreenState } from '../contracts/ws'

export type ConfirmedBoard = Omit<CvBoardUpdate, 'kind'>

export interface DisplayState {
  /** null = snapshot 受信前 */
  screen: ScreenState | null
  lang: Lang
  /** 最新の確定盤面(未確定なら null) */
  board: ConfirmedBoard | null
  /** 最後に受信した判定結果(演出用。seq で新旧を区別する) */
  lastJudge: Judge | null
}

export const initialDisplayState: DisplayState = {
  screen: null,
  lang: 'ja',
  board: null,
  lastJudge: null,
}

/** 受信メッセージを状態に畳み込む。未知の type は無視する(契約) */
export function reduceDisplay(state: DisplayState, msg: DisplayMessage): DisplayState {
  const screen = state.screen
  switch (msg.type) {
    case 'snapshot': {
      const { lang, board, ...rest } = msg.payload
      return { screen: rest as ScreenState, lang, board, lastJudge: null }
    }
    case 'screen':
      return { ...state, screen: msg.payload }
    case 'lang':
      return { ...state, lang: msg.payload.lang }
    case 'board':
      return { ...state, board: msg.payload }
    case 'countdown':
      if (screen?.screen !== 'game_countdown') return state
      return { ...state, screen: { ...screen, ctx: { ...screen.ctx, value: msg.payload.value } } }
    case 'timer':
      if (screen?.screen !== 'game_play') return state
      return {
        ...state,
        screen: { ...screen, ctx: { ...screen.ctx, remaining_ms: msg.payload.remaining_ms } },
      }
    case 'judge': {
      const judge = msg.payload
      if (screen?.screen === 'practice') {
        return {
          ...state,
          lastJudge: judge,
          screen: { ...screen, ctx: { ...screen.ctx, score: judge.total_score } },
        }
      }
      if (screen?.screen === 'game_play') {
        return {
          ...state,
          lastJudge: judge,
          screen: {
            ...screen,
            ctx: { ...screen.ctx, score: judge.total_score, fail_count: judge.fail_count },
          },
        }
      }
      return state
    }
    case 'name':
      if (screen?.screen !== 'result') return state
      return {
        ...state,
        screen: { ...screen, ctx: { ...screen.ctx, name_text: msg.payload.text } },
      }
    case 'ranking':
      if (screen?.screen === 'idle_ranking') {
        return {
          ...state,
          screen: { ...screen, ctx: { ...screen.ctx, entries: msg.payload.entries } },
        }
      }
      if (screen?.screen === 'ranking') {
        return { ...state, screen: { ...screen, ctx: { ...screen.ctx, ...msg.payload } } }
      }
      return state
    default:
      return state
  }
}
