// 盤面表現(契約: docs/contracts/board.md)。frontend/src/contracts/board.ts の写し
// (記録画面は独立パッケージのため複製)。乖離したら契約mdが正。

export type SizeChar = 'L' | 'M' | 'S'
export type TowerName = 'A' | 'B' | 'C'

/** 塔状態インデックス 0〜7(board.md §2 の並び順) */
export const TOWER_STATES = ['', 'S', 'M', 'L', 'MS', 'LS', 'LM', 'LMS'] as const

const TOWER_INDEX = new Map<string, number>(TOWER_STATES.map((s, i) => [s, i]))
const BOARD_RE = /^[LMS]*\/[LMS]*\/[LMS]*$/

export function isLegalTower(tower: string): boolean {
  return TOWER_INDEX.has(tower)
}

/** "LMS//L" -> ["LMS", "", "L"]。形式不正は例外 */
export function parseBoard(board: string): [string, string, string] {
  if (!BOARD_RE.test(board)) throw new Error(`invalid board string: ${board}`)
  return board.split('/') as [string, string, string]
}

export function formatBoard(towers: readonly [string, string, string]): string {
  return towers.join('/')
}

export function isLegalBoard(board: string): boolean {
  if (!BOARD_RE.test(board)) return false
  return parseBoard(board).every(isLegalTower)
}

/** 鏡像盤面(A塔とC塔の入れ替え) */
export function mirrorBoard(board: string): string {
  const [a, b, c] = parseBoard(board)
  return formatBoard([c, b, a])
}

/** 鏡像同一視の正準キー: 盤面と鏡像の辞書順で小さい方 */
export function canonicalKey(board: string): string {
  const mirrored = mirrorBoard(board)
  return board < mirrored ? board : mirrored
}

/** 盤面インデックス 0〜511(board.md §4) */
export function boardIndex(board: string): number {
  const [a, b, c] = parseBoard(board)
  const ia = TOWER_INDEX.get(a)
  const ib = TOWER_INDEX.get(b)
  const ic = TOWER_INDEX.get(c)
  if (ia === undefined || ib === undefined || ic === undefined) {
    throw new Error(`illegal tower in board: ${board}`)
  }
  return ia * 64 + ib * 8 + ic
}

export function boardFromIndex(index: number): string {
  if (!Number.isInteger(index) || index < 0 || index >= 512) {
    throw new Error(`board index out of range: ${index}`)
  }
  return formatBoard([
    TOWER_STATES[Math.floor(index / 64)],
    TOWER_STATES[Math.floor(index / 8) % 8],
    TOWER_STATES[index % 8],
  ])
}

/** 盤面上の箱の総数(得点 = boxCount * 最短手数 の係数) */
export function boxCount(board: string): number {
  return parseBoard(board).reduce((n, tower) => n + tower.length, 0)
}
