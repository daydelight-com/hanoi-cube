// WebSocketメッセージ型(契約: docs/contracts/ws-messages.md, screens.md)。乖離したら契約mdが正。

import type { BoxObservation, CvBoardUpdate } from './cv'

export type Lang = 'ja' | 'en'
export type ButtonName = 'left' | 'right' | 'enter'
// カメラの設置側(back=マット奥側=既定 / front=待機エリア側。front のとき3D視点を180°反転)
export type CameraSide = 'back' | 'front'

// ---- 画面ID・画面別ctx(screens.md) ----

export type ScreenId =
  | 'idle_title'
  | 'idle_ranking'
  | 'mode_select'
  | 'rule_dialog'
  | 'practice'
  | 'game_countdown'
  | 'game_play'
  | 'result'
  | 'ranking'
  | 'qr'

export interface RankingEntry {
  rank: number
  name: string
  score: number
  fail_count: number
  play_id: string
  played_at: string
}

export type CountdownValue = '3' | '2' | '1' | 'go'

export interface ScreenCtxMap {
  idle_title: Record<string, never>
  idle_ranking: { entries: RankingEntry[] }
  mode_select: { focus: 'rules' | 'practice' | 'game' | 'lang' }
  rule_dialog: { from: 'mode_select' | 'practice'; page: number; page_count: number }
  practice: { score: number; selection: 'back' | 'help' | null }
  game_countdown: { value: CountdownValue }
  game_play: { score: number; fail_count: number; remaining_ms: number }
  result: {
    score: number
    fail_count: number
    rank: number
    name_text: string
    focus: 'input' | 'decide'
    input_mode: 'buttons' | 'name'
  }
  ranking: { entries: RankingEntry[]; highlight_play_id: string | null }
  qr: { url: string; play_id: string }
}

export type ScreenState = {
  [K in ScreenId]: { screen: K; ctx: ScreenCtxMap[K] }
}[ScreenId]

// ---- 判定・効果音 ----

export type JudgeResultKind = 'scored' | 'unclearable' | 'duplicate_same' | 'duplicate_mirror'

export interface Judge {
  seq: number
  result: JudgeResultKind
  points: number
  min_moves: number | null
  board: string
  total_score: number
  fail_count: number
}

export type SfxId =
  | 'cursor'
  | 'decide'
  | 'back'
  | 'count'
  | 'go'
  | 'judge_success'
  | 'judge_fail'
  | 'judge_dup'
  | 'tick10'
  | 'timeup'
  | 'rank_tick'
  | 'fanfare'
  | 'key_touch'
  | 'pad_button'
  | 'pad_flash'

// ---- サーバー → ディスプレイ(/ws/display) ----

export type DisplayMessage =
  | {
      type: 'snapshot'
      // board = 最新の確定盤面(未確定なら null)。再接続時の復元に使う
      payload: ScreenState & {
        lang: Lang
        board: Omit<CvBoardUpdate, 'kind'> | null
        camera_side: CameraSide
      }
    }
  | { type: 'screen'; payload: ScreenState }
  | { type: 'lang'; payload: { lang: Lang } }
  | { type: 'boxes'; payload: { t_ms: number; boxes: BoxObservation[] } }
  | { type: 'board'; payload: Omit<CvBoardUpdate, 'kind'> }
  | { type: 'countdown'; payload: { value: CountdownValue } }
  | { type: 'timer'; payload: { remaining_ms: number } }
  | { type: 'judge'; payload: Judge }
  | { type: 'name'; payload: { text: string } }
  | { type: 'ranking'; payload: { entries: RankingEntry[]; highlight_play_id: string | null } }
  | { type: 'sfx'; payload: { id: SfxId } }

// ---- サーバー → iPad(/ws/controller) ----

export type ControllerInputMode = 'buttons' | 'name'

export type ControllerMessage =
  | {
      type: 'snapshot'
      payload: { screen: ScreenId; lang: Lang; input_mode: ControllerInputMode; name_text: string }
    }
  | { type: 'input_mode'; payload: { mode: ControllerInputMode; name_text: string } }
  | { type: 'lang'; payload: { lang: Lang } }
  | { type: 'sfx'; payload: { id: SfxId } }
  | { type: 'flash'; payload: { result: 'scored' | 'failed' | 'duplicate' } }

// ---- iPad → サーバー(/ws/controller) ----

export type ControllerToServerMessage =
  | { type: 'button'; payload: { button: ButtonName } }
  | { type: 'name_text'; payload: { text: string } }
  | { type: 'name_done'; payload: Record<string, never> }
