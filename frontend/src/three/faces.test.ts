import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import { FACE_BY_MATERIAL_INDEX } from './faces'
import { MAT_TO_THREE_QUAT } from './layout'

// 要判断(handoff/S3.md)で定めた面→マット法線の対応(無回転時)
const FACE_NORMALS_MAT: Record<number, [number, number, number]> = {
  1: [0, 0, 1], // 上
  2: [0, -1, 0], // 手前
  3: [1, 0, 0], // 右
  4: [0, 1, 0], // 奥
  5: [-1, 0, 0], // 左
  6: [0, 0, -1], // 底
}

// three.BoxGeometry のマテリアル順に対応するローカル法線
const THREE_NORMALS: [number, number, number][] = [
  [1, 0, 0],
  [-1, 0, 0],
  [0, 1, 0],
  [0, -1, 0],
  [0, 0, 1],
  [0, 0, -1],
]

describe('FACE_BY_MATERIAL_INDEX', () => {
  it('面1〜6がちょうど1回ずつ現れる', () => {
    expect([...FACE_BY_MATERIAL_INDEX].sort()).toEqual([1, 2, 3, 4, 5, 6])
  })

  it('各マテリアルの three 法線をマット座標系に戻すと、その面の定義法線に一致する', () => {
    const threeToMat = MAT_TO_THREE_QUAT.clone().invert()
    FACE_BY_MATERIAL_INDEX.forEach((face, i) => {
      const normalMat = new THREE.Vector3(...THREE_NORMALS[i]).applyQuaternion(threeToMat)
      const expected = new THREE.Vector3(...FACE_NORMALS_MAT[face])
      expect(normalMat.distanceTo(expected), `material ${i} → 面${face}`).toBeCloseTo(0)
    })
  })

  it('面1(上)は three +y のマテリアルに割り当たる', () => {
    expect(FACE_BY_MATERIAL_INDEX[2]).toBe(1)
  })
})
