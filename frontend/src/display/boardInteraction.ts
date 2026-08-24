import type { BoxId, CvBoardUpdate } from '../contracts/cv'

type ConfirmedBoard = Omit<CvBoardUpdate, 'kind'>

/** マウスで選べるのは待機中の箱、または各塔の最上段だけ。 */
export function isSelectableBox(board: ConfirmedBoard | null, boxId: BoxId): boolean {
  if (board === null) return false
  if (board.staging_box_ids.includes(boxId)) return true
  return board.tower_box_ids.some((tower) => tower.at(-1) === boxId)
}

/** 箱が載っている塔。選択済みの箱を積むときのクリック先に使う。 */
export function towerForBox(board: ConfirmedBoard | null, boxId: BoxId): 'A' | 'B' | 'C' | null {
  if (board === null) return null
  const index = board.tower_box_ids.findIndex((tower) => tower.includes(boxId))
  return index === -1 ? null : (['A', 'B', 'C'] as const)[index]
}

export async function moveMockBox(boxId: BoxId, target: 'A' | 'B' | 'C'): Promise<void> {
  const response = await fetch('/api/mock/move', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ box_id: boxId, target }),
  })
  if (!response.ok) throw new Error(`mock move failed (${response.status})`)
}
