// iPadコントローラ効果音の導出(純ロジック)。ws-messages.md §4 の表の通り、
// pad_button は押下時のローカル再生(ControllerApp 側で直接 play)、
// pad_flash は flash 受信、sfx 受信は無条件で再生する。

import type { ControllerMessage, SfxId } from '../contracts/ws'

export function deriveControllerSfx(msg: ControllerMessage): SfxId[] {
  switch (msg.type) {
    case 'flash':
      return ['pad_flash']
    case 'sfx':
      return [msg.payload.id]
    default:
      return []
  }
}
