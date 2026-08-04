// CV検出結果の型(契約: docs/contracts/cv-interface.md)。乖離したら契約mdが正。
// ディスプレイはこの型を ws の boxes / board メッセージとして受信する。

export type BoxSize = 'large' | 'medium' | 'small'
export type Area = 'A' | 'B' | 'C' | 'staging'
export type ViolationType = 'size_order' | 'duplicate_size' | 'overflow'

export const BOX_IDS = [
  'large-1',
  'large-2',
  'large-3',
  'medium-1',
  'medium-2',
  'medium-3',
  'small-1',
  'small-2',
  'small-3',
] as const

export type BoxId = (typeof BOX_IDS)[number]

/** 箱の一辺(mm)。3D表示のスケールに使う */
export const BOX_EDGE_MM: Record<BoxSize, number> = { large: 75, medium: 50, small: 30 }

export interface BoxObservation {
  box_id: BoxId
  size: BoxSize
  /** マット座標系での箱の底面中心 [x, y, z](mm) */
  pos_mm: [number, number, number]
  /** 姿勢クォータニオン [x, y, z, w] */
  quat: [number, number, number, number]
  /** null = 移動中・掴まれ中 */
  area: Area | null
  /** 塔内の段(下から0)。塔以外は null */
  level: number | null
  /** false = タグロスト中(保持位置) */
  visible: boolean
  seen_tag_ids: number[]
}

export interface CvFrame {
  kind: 'frame'
  t_ms: number
  mat_corners_detected: number
  /** 常に9箱すべて */
  boxes: BoxObservation[]
}

export interface Violation {
  tower: 'A' | 'B' | 'C'
  type: ViolationType
}

export interface CvBoardUpdate {
  kind: 'board'
  t_ms: number
  /** A/B/C の生スタック(下から上)。違反時は "SL" 等もあり得る */
  towers: [string, string, string]
  /** "/".join(towers)。legal=true のとき board.md の正準形 */
  board: string
  legal: boolean
  violations: Violation[]
  staging_box_ids: BoxId[]
}
