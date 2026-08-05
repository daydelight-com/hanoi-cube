// 10画面を3つの音楽フェーズへまとめる。フェーズ内の画面遷移では同じ曲を
// 継続し、タイトル⇄待機ランキングやリザルト→ランキング→QRで頭出ししない。

import type { ScreenId } from '../contracts/ws'
import type { BgmTrackId } from './tracks'

const WAITING_SCREENS: ReadonlySet<ScreenId> = new Set([
  'idle_title',
  'idle_ranking',
  'mode_select',
  'rule_dialog',
  'practice',
])

const RESULT_SCREENS: ReadonlySet<ScreenId> = new Set(['result', 'ranking', 'qr'])

/**
 * カウントダウン中は3・2・1・GOの効果音を主役にするため無音にし、
 * game_play 入場（GOと同時）で本番曲を頭から始める。
 */
export function bgmTrackForScreen(screen: ScreenId | null): BgmTrackId | null {
  if (screen === null || screen === 'game_countdown') return null
  if (screen === 'game_play') return 'gameplay'
  if (WAITING_SCREENS.has(screen)) return 'waiting'
  if (RESULT_SCREENS.has(screen)) return 'result'
  return null
}
