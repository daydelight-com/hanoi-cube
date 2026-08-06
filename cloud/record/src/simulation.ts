// 最短手順シミュレーション(仕様§5.10)。
// 判定時の tower_box_ids を初期状態として min_path を順に適用する。
// min_path は {size, from, to} のみだが、動かすのは常に from 塔の最上段なので
// 個体は一意に定まる(docs/contracts/firestore.md §1)。

import type { SizeChar } from './contracts/board'
import type { Move } from './contracts/precompute'
import type { TowerBoxIds } from './contracts/play'

const TOWER_AT = { A: 0, B: 1, C: 2 } as const

const SIZE_OF_NAME: Record<string, SizeChar> = { large: 'L', medium: 'M', small: 'S' }

/** 箱ID "large-2" → サイズ 'L'。未知の形式は例外 */
export function boxSize(boxId: string): SizeChar {
  const size = SIZE_OF_NAME[boxId.split('-')[0]]
  if (!size) throw new Error(`unknown box id: ${boxId}`)
  return size
}

/** 箱ID "large-2" → 個体番号 2(同サイズ3個を見分けるラベル) */
export function boxSerial(boxId: string): string {
  return boxId.split('-')[1] ?? '?'
}

export interface StepResult {
  stacks: TowerBoxIds
  movedBoxId: string
}

/** 1手を適用する(元の配列は変更しない)。from塔の最上段のサイズが合わなければ例外 */
export function applyMove(stacks: TowerBoxIds, move: Move): StepResult {
  const next: TowerBoxIds = [[...stacks[0]], [...stacks[1]], [...stacks[2]]]
  const fromTower = next[TOWER_AT[move.from]]
  const boxId = fromTower.pop()
  if (boxId === undefined || boxSize(boxId) !== move.size) {
    throw new Error(`move ${move.size} ${move.from}->${move.to} does not fit ${stacks.join('|')}`)
  }
  next[TOWER_AT[move.to]].push(boxId)
  return { stacks: next, movedBoxId: boxId }
}

/** 初期状態に moves の先頭 steps 手を適用した状態と、最後に動いた箱を返す */
export function stacksAfter(
  initial: TowerBoxIds,
  moves: readonly Move[],
  steps: number,
): { stacks: TowerBoxIds; movedBoxId: string | null } {
  let stacks = initial
  let movedBoxId: string | null = null
  for (const move of moves.slice(0, steps)) {
    const result = applyMove(stacks, move)
    stacks = result.stacks
    movedBoxId = result.movedBoxId
  }
  return { stacks, movedBoxId }
}

/** 盤面文字列との一致確認用: 各塔のサイズ列(下から上) */
export function sizeTowers(stacks: TowerBoxIds): [string, string, string] {
  return stacks.map((tower) => tower.map(boxSize).join('')) as [string, string, string]
}
