// フレームレート非依存の指数平滑化。CVストリームは約30fps・モックは離散ジャンプだが、
// 描画は毎フレーム目標値へ収束させることで 60fps の滑らかな移動にする。

/** 経過時間 dt(秒)に対する平滑化係数(0..1)。lambda は収束速度(1/秒) */
export function dampFactor(lambda: number, dtSec: number): number {
  return 1 - Math.exp(-lambda * dtSec)
}

/** 位置の収束速度。約0.2秒で目標値の9割に到達する */
export const POS_LAMBDA = 12

/** 姿勢の収束速度 */
export const ROT_LAMBDA = 12
