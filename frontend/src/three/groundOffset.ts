// 接地補正(表示専用): キャリブレーションのマット面推定が実際と数mm〜十数mmずれると、
// 接地している箱の底面 z が 0 からずれ、3D表示で「埋まる/浮く」ように見える。
// 「塔の最下段(level=0)と判定済みの箱の底面は物理的に z=0」という事実を使って
// ずれの平均を推定し、可視箱の描画高さにだけ補正として足す。
// サーバー側の判定(area/level/積み許容)には一切影響しない。

import type { BoxObservation } from '../contracts/cv'

/** 補正量の上限(mm)。これを超えるずれは先に判定側(積み許容25mm)が破綻する領域 */
export const GROUND_OFFSET_MAX_MM = 25

/** boxes 更新1回あたりの追従率。約30fps入力で1秒弱で9割収束する */
export const GROUND_OFFSET_GAIN = 0.08

/** 接地箱(可視かつ level=0)の底面zの平均(mm)。接地箱がなければ null */
export function measuredGroundErrorMm(boxes: readonly BoxObservation[]): number | null {
  const grounded = boxes.filter((b) => b.visible && b.level === 0)
  if (grounded.length === 0) return null
  return grounded.reduce((sum, b) => sum + b.pos_mm[2], 0) / grounded.length
}

/**
 * 補正量(mm)を1ステップ更新する。接地箱が見えない間は現在値を保持し、
 * 見えている間はずれを打ち消す値(±上限内)へ指数的に追従する。
 */
export function nextGroundOffsetMm(currentMm: number, boxes: readonly BoxObservation[]): number {
  const error = measuredGroundErrorMm(boxes)
  if (error === null) return currentMm
  const target = Math.max(-GROUND_OFFSET_MAX_MM, Math.min(GROUND_OFFSET_MAX_MM, -error))
  return currentMm + (target - currentMm) * GROUND_OFFSET_GAIN
}
