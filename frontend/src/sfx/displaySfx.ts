// ディスプレイ効果音の導出(純ロジック)。受信メッセージと直前状態から
// 鳴らすべき SfxId を決める(発火方式は ws-messages.md §4 の表で確定済み:
// 全音クライアント自律。サーバーの sfx 受信は無条件で再生)。
//
// ガードを満たさない操作はサーバーが何も送らないため、ここに届いた時点で
// 「音を出してよいイベント」だけが来る(screens.md §3 注記)。
// snapshot は再接続復元のため無音。rank_tick / fanfare はメッセージ起点ではなく
// せり上がり演出のタイマー起点(IdleRankingScreen 側)。

import type { DisplayMessage, ScreenId, ScreenState, SfxId } from '../contracts/ws'
import type { DisplayState } from '../display/store'

export interface SfxEvent {
  id: SfxId
  /** judge_success の獲得点(音の豪華さに反映) */
  points?: number
}

// 画面遷移 → 遷移音(前進=decide / 後退=back)。表にない遷移は無音:
// - mode_select→game_countdown は直後の count「3」がフィードバックを兼ねる
// - game_countdown→game_play は go、game_play→result は timeup が代替
// - idle_title⇄idle_ranking はタイムアウト遷移と区別できない
const TRANSITION_SFX: Partial<Record<ScreenId, Partial<Record<ScreenId, SfxId>>>> = {
  idle_title: { mode_select: 'decide' },
  mode_select: { rule_dialog: 'decide', practice: 'decide' },
  rule_dialog: { mode_select: 'back', practice: 'back' },
  practice: { mode_select: 'back', rule_dialog: 'decide' },
  result: { ranking: 'decide' },
  ranking: { qr: 'decide' },
  qr: { idle_title: 'decide' },
}

/** 同一画面内の ctx 変化 → カーソル/決定音 */
function sameScreenSfx(prev: ScreenState, next: ScreenState): SfxEvent[] {
  if (prev.screen === 'mode_select' && next.screen === 'mode_select') {
    return prev.ctx.focus !== next.ctx.focus ? [{ id: 'cursor' }] : []
  }
  if (prev.screen === 'rule_dialog' && next.screen === 'rule_dialog') {
    return prev.ctx.page !== next.ctx.page ? [{ id: 'cursor' }] : []
  }
  if (prev.screen === 'practice' && next.screen === 'practice') {
    // 選択の有効化・移動のみ音を出す(box_moved による解除=null は無音)
    return prev.ctx.selection !== next.ctx.selection && next.ctx.selection !== null
      ? [{ id: 'cursor' }]
      : []
  }
  if (prev.screen === 'result' && next.screen === 'result') {
    // 入力モードの切替(再入力・かんりょう)は決定音、focus 移動はカーソル音
    if (prev.ctx.input_mode !== next.ctx.input_mode) return [{ id: 'decide' }]
    if (prev.ctx.focus !== next.ctx.focus) return [{ id: 'cursor' }]
    return []
  }
  return []
}

/** 受信メッセージから効果音イベントを導出する(prev = メッセージ適用前の状態) */
export function deriveDisplaySfx(prev: DisplayState, msg: DisplayMessage): SfxEvent[] {
  const screen = prev.screen
  switch (msg.type) {
    case 'screen': {
      if (screen === null) return [] // 初期 snapshot 前後の復元は無音
      if (screen.screen === msg.payload.screen) return sameScreenSfx(screen, msg.payload)
      const id = TRANSITION_SFX[screen.screen]?.[msg.payload.screen]
      return id !== undefined ? [{ id }] : []
    }
    case 'countdown':
      if (screen?.screen !== 'game_countdown') return []
      return msg.payload.value === 'go' ? [{ id: 'go' }] : [{ id: 'count' }]
    case 'timer': {
      if (screen?.screen !== 'game_play') return []
      const remaining = msg.payload.remaining_ms
      if (remaining <= 0) return [{ id: 'timeup' }]
      return remaining < 10_000 ? [{ id: 'tick10' }] : []
    }
    case 'judge': {
      if (screen?.screen !== 'practice' && screen?.screen !== 'game_play') return []
      const result = msg.payload.result
      if (result === 'scored') return [{ id: 'judge_success', points: msg.payload.points }]
      if (result === 'unclearable') return [{ id: 'judge_fail' }]
      return [{ id: 'judge_dup' }]
    }
    case 'name':
      if (screen?.screen !== 'result') return []
      return msg.payload.text !== screen.ctx.name_text ? [{ id: 'key_touch' }] : []
    case 'lang':
      // 言語トグル(mode_select 行9)のみ。待機入場時のjaリセットは別画面で届くため無音
      return screen?.screen === 'mode_select' ? [{ id: 'cursor' }] : []
    case 'sfx':
      return [{ id: msg.payload.id }]
    default:
      // snapshot / boxes / board / ranking は無音
      return []
  }
}
