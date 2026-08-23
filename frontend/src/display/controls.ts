// ディスプレイ上のメニューを、状態機械が受け付ける3ボタン操作へ変換する。
// 画面の表示状態を楽観更新せず、操作後はサーバーから返る screen を唯一の正とする。

import type { ButtonName } from '../contracts/ws'

export function modeSelectionButtons(
  current: 'rules' | 'practice' | 'game' | 'lang',
  target: 'rules' | 'practice' | 'game' | 'lang',
): ButtonName[] {
  const order = ['rules', 'practice', 'game', 'lang'] as const
  const currentIndex = order.indexOf(current)
  const targetIndex = order.indexOf(target)
  return [
    ...Array((targetIndex - currentIndex + order.length) % order.length).fill('right'),
    'enter',
  ]
}

export function focusedSelectionButtons<T extends string>(
  current: T | null,
  target: T,
  buttonForTarget: (target: T) => 'left' | 'right',
): ButtonName[] {
  return current === target ? ['enter'] : [buttonForTarget(target), 'enter']
}
