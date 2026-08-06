// plays/{play_id} ドキュメントのTS写し(契約: docs/contracts/firestore.md §1)。
// 乖離したら契約mdが正。

export type JudgeResult = 'scored' | 'unclearable' | 'duplicate_same' | 'duplicate_mirror'

/** 判定時に各塔にあった箱の個体(下から上)のタプル表現(他契約と同形。表示ロジック用) */
export type TowerBoxIds = [string[], string[], string[]]

/** Firestore ドキュメント上の表現。配列の直接入れ子を保存できないため a/b/c のマップ */
export interface TowerBoxIdsDoc {
  a: string[]
  b: string[]
  c: string[]
}

export function towerTuple(doc: TowerBoxIdsDoc): TowerBoxIds {
  return [doc.a, doc.b, doc.c]
}

export interface JudgementDoc {
  seq: number
  board: string
  elapsed_ms: number
  result: JudgeResult
  points: number
  min_moves: number | null
  dup_of_seq: number | null
  tower_box_ids: TowerBoxIdsDoc
}

export interface PlayDoc {
  player_name: string
  score: number
  fail_count: number
  played_at: string
  judgements: JudgementDoc[]
}

/** Firestore から読んだ生データの外形チェック(表示に必要な範囲のみ) */
export function isPlayDoc(value: unknown): value is PlayDoc {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.player_name === 'string' &&
    typeof v.score === 'number' &&
    typeof v.fail_count === 'number' &&
    typeof v.played_at === 'string' &&
    Array.isArray(v.judgements)
  )
}
