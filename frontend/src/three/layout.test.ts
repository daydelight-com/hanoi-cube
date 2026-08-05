import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import { MAT_TO_THREE_QUAT, TOWER_X_MM, TOWER_Y_MM, matPosToThree, matQuatToThree } from './layout'

function toArray(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z]
}

describe('matPosToThree', () => {
  it('マット中心(床面)が three 原点になる', () => {
    const out = new THREE.Vector3()
    matPosToThree([210, 148.5, 0], out)
    expect(toArray(out).map((n) => Math.round(n * 1e6) / 1e6)).toEqual([0, 0, 0])
  })

  it('マット原点(左手前)は左・手前・床になる', () => {
    const out = new THREE.Vector3()
    matPosToThree([0, 0, 0], out)
    expect(out.x).toBeCloseTo(-210)
    expect(out.y).toBeCloseTo(0)
    expect(out.z).toBeCloseTo(148.5) // 手前 = +z
  })

  it('塔C位置・高さ75mm(mat 315,207.9,75)', () => {
    const out = new THREE.Vector3()
    matPosToThree([TOWER_X_MM.C, TOWER_Y_MM, 75], out)
    expect(out.x).toBeCloseTo(105)
    expect(out.y).toBeCloseTo(75) // マットzの高さ → three y
    expect(out.z).toBeCloseTo(-59.4) // 奥 = -z
  })
})

describe('matQuatToThree', () => {
  it('単位クォータニオンは単位のまま', () => {
    const out = new THREE.Quaternion()
    matQuatToThree([0, 0, 0, 1], out)
    expect(out.angleTo(new THREE.Quaternion())).toBeCloseTo(0)
  })

  it('マットz軸まわり90°回転は three y軸まわり90°回転になる', () => {
    // マット座標系: z軸(上)まわりに90°回すと x軸(右)→ y軸(奥)
    const matQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2)
    const out = new THREE.Quaternion()
    matQuatToThree([matQuat.x, matQuat.y, matQuat.z, matQuat.w], out)
    // three座標系での期待: 右(+x)→ 奥(-z)
    const v = new THREE.Vector3(1, 0, 0).applyQuaternion(out)
    expect(v.x).toBeCloseTo(0)
    expect(v.y).toBeCloseTo(0)
    expect(v.z).toBeCloseTo(-1)
  })

  it('基底変換の恒等式: 任意軸の回転で回した mat ベクトルが three 側でも一致する', () => {
    const axisMat = new THREE.Vector3(1, 2, 3).normalize()
    const matQuat = new THREE.Quaternion().setFromAxisAngle(axisMat, 1.1)
    const out = new THREE.Quaternion()
    matQuatToThree([matQuat.x, matQuat.y, matQuat.z, matQuat.w], out)

    const vMat = new THREE.Vector3(0.4, -0.5, 0.7)
    // mat 側で回してから three へ変換
    const a = vMat.clone().applyQuaternion(matQuat).applyQuaternion(MAT_TO_THREE_QUAT)
    // three へ変換してから three 側で回す
    const b = vMat.clone().applyQuaternion(MAT_TO_THREE_QUAT).applyQuaternion(out)
    expect(a.distanceTo(b)).toBeCloseTo(0)
  })
})
