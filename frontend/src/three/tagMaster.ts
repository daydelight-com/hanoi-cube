// タグマスタ(scripts/generate_tag_sheet.py が生成する output/tag_master.json)の読み込み。
// CVのID割当と3Dテクスチャで同一マスタを共用する(仕様§5.1)。実データは
// `npm run sync-tags` で frontend/public/tags/ に同期したコピーを配信する。

import type { BoxId, BoxSize } from '../contracts/cv'

export interface BoxTagEntry {
  id: number
  box: BoxId
  box_label: string
  size: BoxSize
  box_mm: number
  face: number
  tag_mm: number
  black_mm: number
  placement: 'top_right' | 'center'
}

export interface TagMaster {
  family: string
  faces_per_box: number
  box_tags: BoxTagEntry[]
  mat_tags: { id: number; corner: string; tag_mm: number; black_mm: number }[]
}

export function tagImageUrl(id: number): string {
  return `/tags/tag36_11_${String(id).padStart(5, '0')}.png`
}

export async function fetchTagMaster(): Promise<TagMaster> {
  const res = await fetch('/tags/tag_master.json')
  if (!res.ok) throw new Error(`tag_master.json: HTTP ${res.status}`)
  return (await res.json()) as TagMaster
}

/** (箱, 面) → タグエントリの索引 */
export function indexBoxTags(master: TagMaster): Map<string, BoxTagEntry> {
  return new Map(master.box_tags.map((t) => [`${t.box}/${t.face}`, t]))
}
