// マット座標系(cv-interface.md §2)と three.js 座標系の対応。
// マット寸法・塔/待機エリア位置はモックCV(server/app/cv/mock.py 冒頭)の合成レイアウトと同値。
// 実CV(S8)ではキャリブレーション結果に依らずマット座標系(mm)で届くため、この定数は表示専用。

import * as THREE from 'three'

export const MAT_SIZE_MM = { x: 600, y: 400 } as const
export const TOWER_X_MM = { A: 150, B: 300, C: 450 } as const
export const TOWER_Y_MM = 280
export const STAGING_Y_MM = 80
export const STAGING_X0_MM = 60
export const STAGING_PITCH_MM = 60

// マット座標系: 左手前隅が原点、x=右、y=奥、z=上(mm)
// three 座標系: マット中心が原点、x=右、y=上、z=手前(カメラ側)
//   three.x = mat.x - 300 / three.y = mat.z / three.z = -(mat.y - 200)
// これは x 軸まわり -90° の回転+平行移動に一致する。

const MAT_CENTER = new THREE.Vector3(MAT_SIZE_MM.x / 2, MAT_SIZE_MM.y / 2, 0)

/** マット座標系→three座標系の回転(x軸まわり -90°) */
export const MAT_TO_THREE_QUAT = new THREE.Quaternion().setFromAxisAngle(
  new THREE.Vector3(1, 0, 0),
  -Math.PI / 2,
)

/** マット座標(mm)を three 座標に変換して out に書き込む */
export function matPosToThree(pos: readonly [number, number, number], out: THREE.Vector3): void {
  out.set(pos[0], pos[1], pos[2]).sub(MAT_CENTER).applyQuaternion(MAT_TO_THREE_QUAT)
}

/** マット座標系の姿勢クォータニオン [x,y,z,w] を three 座標系に変換して out に書き込む */
export function matQuatToThree(
  quat: readonly [number, number, number, number],
  out: THREE.Quaternion,
): void {
  // 基底変換: q_three = r * q_mat * r⁻¹
  out.set(quat[0], quat[1], quat[2], quat[3])
  out.premultiply(MAT_TO_THREE_QUAT)
  out.multiply(_matToThreeInv)
}

const _matToThreeInv = MAT_TO_THREE_QUAT.clone().invert()
