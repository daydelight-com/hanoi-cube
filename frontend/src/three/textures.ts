// 仮テクスチャ生成(仕様§5.1: ロゴ確定まではサイズ別の色分け+タグで進める)。
// タグの寸法・位置は tag_master.json 準拠(タグ実寸/箱実寸の比で面上に配置する)。

import * as THREE from 'three'
import type { BoxSize } from '../contracts/cv'
import type { BoxTagEntry } from './tagMaster'
import { tagImageUrl } from './tagMaster'

/** サイズ別の面ベースカラー(レトロアーケード風。ロゴ確定までの仮) */
export const SIZE_COLOR: Record<BoxSize, string> = {
  large: '#c0392b',
  medium: '#438532',
  small: '#2e6da4',
}

/** 物理の貼付余白(mm)。タグシールを面の隅から離す距離(仮値) */
const TAG_MARGIN_MM = 3

export interface TagRect {
  /** 面の左端からタグ左端まで(面幅=1 の割合) */
  x: number
  /** 面の上端からタグ上端まで(面幅=1 の割合) */
  y: number
  /** タグの一辺(面幅=1 の割合) */
  size: number
}

/** 面上のタグ配置(placement と実寸比から計算)。純関数・テスト対象 */
export function tagRect(entry: Pick<BoxTagEntry, 'box_mm' | 'tag_mm' | 'placement'>): TagRect {
  const size = Math.min(entry.tag_mm / entry.box_mm, 1)
  if (entry.placement === 'top_right') {
    const margin = TAG_MARGIN_MM / entry.box_mm
    const x = Math.max(1 - size - margin, 0)
    return { x, y: Math.min(margin, 1 - size), size }
  }
  return { x: (1 - size) / 2, y: (1 - size) / 2, size }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`failed to load ${url}`))
    img.src = url
  })
}

const FACE_PX = 256

/** 1面ぶんの仮テクスチャを描く(色分け+タグ+ラベル) */
export function drawFaceCanvas(
  entry: BoxTagEntry,
  tagImg: CanvasImageSource | null,
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = FACE_PX
  canvas.height = FACE_PX
  const g = canvas.getContext('2d')
  if (!g) return canvas

  g.fillStyle = SIZE_COLOR[entry.size]
  g.fillRect(0, 0, FACE_PX, FACE_PX)
  // 縁取り(箱の稜線を見せる)
  g.strokeStyle = 'rgba(0, 0, 0, 0.45)'
  g.lineWidth = Math.max(4, FACE_PX * 0.03)
  g.strokeRect(0, 0, FACE_PX, FACE_PX)

  // ラベル(仮ロゴ相当): 箱ラベル+面番号
  g.fillStyle = 'rgba(255, 255, 255, 0.92)'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.font = `bold ${Math.round(FACE_PX * 0.3)}px sans-serif`
  g.fillText(entry.box_label, FACE_PX / 2, FACE_PX * 0.52)
  g.font = `${Math.round(FACE_PX * 0.11)}px sans-serif`
  g.fillText(`面${entry.face}`, FACE_PX / 2, FACE_PX * 0.78)

  if (tagImg) {
    const rect = tagRect(entry)
    g.imageSmoothingEnabled = false
    g.drawImage(
      tagImg,
      rect.x * FACE_PX,
      rect.y * FACE_PX,
      rect.size * FACE_PX,
      rect.size * FACE_PX,
    )
  }
  return canvas
}

/** 1箱ぶんの6面テクスチャを面番号(1〜6)→テクスチャの Map で返す */
export async function buildBoxFaceTextures(
  entries: BoxTagEntry[],
): Promise<Map<number, THREE.CanvasTexture>> {
  const textures = new Map<number, THREE.CanvasTexture>()
  await Promise.all(
    entries.map(async (entry) => {
      const img = await loadImage(tagImageUrl(entry.id)).catch(() => null)
      const texture = new THREE.CanvasTexture(drawFaceCanvas(entry, img))
      texture.colorSpace = THREE.SRGBColorSpace
      texture.anisotropy = 4
      textures.set(entry.face, texture)
    }),
  )
  return textures
}

// ---- マット ----

const MAT_PX_PER_MM = 2

/** プレイマットの仮テクスチャ(A/B/C 塔+待機エリア+四隅タグ)。
 *  レイアウト定数は layout.ts(=モックCVの合成レイアウト)と同じものを使う */
export async function buildMatTexture(layout: {
  matSize: { x: number; y: number }
  towerX: Record<'A' | 'B' | 'C', number>
  towerY: number
  stagingY: number
  matTags: { id: number; corner: string; tag_mm: number }[]
}): Promise<THREE.CanvasTexture> {
  const w = layout.matSize.x * MAT_PX_PER_MM
  const h = layout.matSize.y * MAT_PX_PER_MM
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const g = canvas.getContext('2d')
  if (g) {
    // canvas座標: 左上 = マット左奥 (0, y_max)。canvasY = (y_max - mat.y) * scale
    const px = (mm: number) => mm * MAT_PX_PER_MM
    const cy = (yMm: number) => h - px(yMm)

    g.fillStyle = '#10240f'
    g.fillRect(0, 0, w, h)
    g.strokeStyle = 'rgba(67, 133, 50, 0.35)'
    g.lineWidth = 2
    for (let x = 0; x <= layout.matSize.x; x += 50) {
      g.beginPath()
      g.moveTo(px(x), 0)
      g.lineTo(px(x), h)
      g.stroke()
    }
    for (let y = 0; y <= layout.matSize.y; y += 50) {
      g.beginPath()
      g.moveTo(0, cy(y))
      g.lineTo(w, cy(y))
      g.stroke()
    }

    // 塔エリア(大箱75mmが収まる 90mm 枠)
    g.textAlign = 'center'
    for (const tower of ['A', 'B', 'C'] as const) {
      const x = px(layout.towerX[tower])
      const y = cy(layout.towerY)
      g.strokeStyle = '#7ee06a'
      g.lineWidth = 4
      g.strokeRect(x - px(45), y - px(45), px(90), px(90))
      g.fillStyle = 'rgba(126, 224, 106, 0.85)'
      g.font = `bold ${px(28)}px sans-serif`
      g.fillText(tower, x, y + px(58) + px(10))
    }

    // 待機エリア(手前の横長ゾーン)
    g.strokeStyle = 'rgba(126, 224, 106, 0.6)'
    g.lineWidth = 3
    g.strokeRect(px(30), cy(layout.stagingY + 50), w - px(60), px(100))

    // 四隅のキャリブレーションタグ(46mm)
    const tagPositions: Record<string, [number, number]> = {
      左上: [0, 0],
      右上: [w - px(46), 0],
      右下: [w - px(46), h - px(46)],
      左下: [0, h - px(46)],
    }
    await Promise.all(
      layout.matTags.map(async (tag) => {
        const pos = tagPositions[tag.corner]
        if (!pos) return
        const img = await loadImage(tagImageUrl(tag.id)).catch(() => null)
        if (!img) return
        g.imageSmoothingEnabled = false
        g.drawImage(img, pos[0], pos[1], px(tag.tag_mm), px(tag.tag_mm))
      }),
    )
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}
