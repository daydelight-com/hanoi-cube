// 面番号(tag_master.json の face 1〜6)と箱ローカル軸の対応。
//
// cv-interface.md は「quat 単位 = 面1が上」のみ規定し、面2〜6 の向きは未規定
// (物理の貼付も「どの面を面1にするかは自由」)。表示と実CV(S8)で同じ対応を
// 使うため、ここを正とする(要判断 → handoff/S3.md):
//   面1=+z(上) 面2=-y(手前) 面3=+x(右) 面4=+y(奥) 面5=-x(左) 面6=-z(底)
// いずれもマット座標系での無回転時の向き。

/** three.BoxGeometry のマテリアル順(+x,-x,+y,-y,+z,-z)に並べた面番号。
 *  箱ローカル軸は無回転時に three.x=マットx(右), three.y=マットz(上), three.z=マット-y(手前) */
export const FACE_BY_MATERIAL_INDEX: readonly [number, number, number, number, number, number] = [
  3, // three +x = マット +x = 面3(右)
  5, // three -x = マット -x = 面5(左)
  1, // three +y = マット +z = 面1(上)
  6, // three -y = マット -z = 面6(底)
  2, // three +z = マット -y = 面2(手前)
  4, // three -z = マット +y = 面4(奥)
]
