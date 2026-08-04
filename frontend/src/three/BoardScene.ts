// 3D盤面シーン: マット+箱9個。CvFrame の boxes(約30fps)を目標値として受け取り、
// 描画ループ(60fps)で指数平滑化しながら追従させる。React には依存しない。

import * as THREE from 'three'
import type { BoxObservation, BoxId, BoxSize } from '../contracts/cv'
import { BOX_EDGE_MM } from '../contracts/cv'
import { FACE_BY_MATERIAL_INDEX } from './faces'
import {
  MAT_SIZE_MM,
  STAGING_Y_MM,
  TOWER_X_MM,
  TOWER_Y_MM,
  matPosToThree,
  matQuatToThree,
} from './layout'
import { POS_LAMBDA, ROT_LAMBDA, dampFactor } from './smoothing'
import { fetchTagMaster } from './tagMaster'
import { SIZE_COLOR, buildBoxFaceTextures, buildMatTexture } from './textures'

const GHOST_OPACITY = 0.35 // タグロスト中(visible=false)の箱の透明度

interface BoxTarget {
  center: THREE.Vector3
  quat: THREE.Quaternion
  visible: boolean
  fresh: boolean // まだ一度も描画位置に反映していない(スナップ対象)
}

interface BoxEntry {
  mesh: THREE.Mesh
  materials: THREE.MeshLambertMaterial[]
  size: BoxSize
  target: BoxTarget
}

export class BoardScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private lastTickMs: number | null = null
  private boxes = new Map<BoxId, BoxEntry>()
  private faceTextures = new Map<BoxId, Map<number, THREE.Texture>>()
  private disposed = false

  // FPS計測(直近1秒の描画フレーム数)。DoD確認用に HUD へ通知する
  private frameCount = 0
  private fpsWindowStart = 0
  onFps: ((fps: number) => void) | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

    this.camera = new THREE.PerspectiveCamera(45, 1, 10, 5000)
    this.camera.position.set(0, 520, 640)
    this.camera.lookAt(0, 40, 0)

    this.scene.background = new THREE.Color('#060d06')
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.9))
    const sun = new THREE.DirectionalLight(0xffffff, 1.6)
    sun.position.set(-250, 600, 400)
    this.scene.add(sun)

    this.buildMat()
    void this.loadTextures()
    this.renderer.setAnimationLoop(() => this.tick())
  }

  /** 最新フレームの箱位置を目標値として設定する(WSの boxes メッセージから呼ぶ) */
  setBoxes(boxes: BoxObservation[]): void {
    for (const obs of boxes) {
      const entry = this.ensureBox(obs.box_id, obs.size)
      const edge = BOX_EDGE_MM[obs.size]
      const t = entry.target
      matPosToThree(obs.pos_mm, t.center)
      matQuatToThree(obs.quat, t.quat)
      // pos_mm は底面中心。箱ローカル上方向に半辺ぶん進めて中心にする
      t.center.add(_up.set(0, edge / 2, 0).applyQuaternion(t.quat))
      t.visible = obs.visible
    }
  }

  setSize(width: number, height: number): void {
    this.renderer.setSize(width, height, false)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
  }

  dispose(): void {
    this.disposed = true
    this.renderer.setAnimationLoop(null)
    // メッシュ未適用のテクスチャ(ロード途中で破棄された場合)も含めて解放する
    this.disposeFaceTextures()
    this.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose()
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material]
        for (const m of materials) {
          if ('map' in m && m.map instanceof THREE.Texture) m.map.dispose()
          m.dispose()
        }
      }
    })
    this.renderer.dispose()
  }

  // ---- 内部 ----

  private tick(): void {
    const now = performance.now()
    const dt = Math.min(this.lastTickMs === null ? 0 : (now - this.lastTickMs) / 1000, 0.1)
    this.lastTickMs = now
    const posK = dampFactor(POS_LAMBDA, dt)
    const rotK = dampFactor(ROT_LAMBDA, dt)
    for (const entry of this.boxes.values()) {
      const t = entry.target
      if (t.fresh) {
        entry.mesh.position.copy(t.center)
        entry.mesh.quaternion.copy(t.quat)
        t.fresh = false
      } else {
        entry.mesh.position.lerp(t.center, posK)
        entry.mesh.quaternion.slerp(t.quat, rotK)
      }
      const opacity = t.visible ? 1 : GHOST_OPACITY
      if (entry.materials[0].opacity !== opacity) {
        for (const m of entry.materials) {
          m.opacity = opacity
          m.transparent = opacity < 1
          m.needsUpdate = true
        }
      }
    }
    this.renderer.render(this.scene, this.camera)

    this.frameCount += 1
    if (this.fpsWindowStart === 0) this.fpsWindowStart = now
    if (now - this.fpsWindowStart >= 1000) {
      this.onFps?.((this.frameCount * 1000) / (now - this.fpsWindowStart))
      this.frameCount = 0
      this.fpsWindowStart = now
    }
  }

  private ensureBox(boxId: BoxId, size: BoxSize): BoxEntry {
    const existing = this.boxes.get(boxId)
    if (existing) return existing
    const edge = BOX_EDGE_MM[size]
    const materials = Array.from(
      { length: 6 },
      () => new THREE.MeshLambertMaterial({ color: SIZE_COLOR[size] }),
    )
    this.applyFaceTextures(boxId, materials)
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(edge, edge, edge), materials)
    this.scene.add(mesh)
    const entry: BoxEntry = {
      mesh,
      materials,
      size,
      target: {
        center: new THREE.Vector3(),
        quat: new THREE.Quaternion(),
        visible: true,
        fresh: true,
      },
    }
    this.boxes.set(boxId, entry)
    return entry
  }

  private applyFaceTextures(boxId: BoxId, materials: THREE.MeshLambertMaterial[]): void {
    const byFace = this.faceTextures.get(boxId)
    if (!byFace) return
    materials.forEach((material, i) => {
      const texture = byFace.get(FACE_BY_MATERIAL_INDEX[i])
      if (texture) {
        material.map = texture
        material.color.set('#ffffff')
        material.needsUpdate = true
      }
    })
  }

  private disposeFaceTextures(): void {
    for (const byFace of this.faceTextures.values()) {
      for (const texture of byFace.values()) texture.dispose()
    }
    this.faceTextures.clear()
  }

  private async loadTextures(): Promise<void> {
    try {
      const master = await fetchTagMaster()
      const byBox = new Map<BoxId, typeof master.box_tags>()
      for (const entry of master.box_tags) {
        const list = byBox.get(entry.box) ?? []
        list.push(entry)
        byBox.set(entry.box, list)
      }
      await Promise.all(
        [...byBox.entries()].map(async ([boxId, entries]) => {
          this.faceTextures.set(boxId, await buildBoxFaceTextures(entries))
        }),
      )
      const matTexture = await buildMatTexture({
        matSize: MAT_SIZE_MM,
        towerX: TOWER_X_MM,
        towerY: TOWER_Y_MM,
        stagingY: STAGING_Y_MM,
        matTags: master.mat_tags,
      })
      if (this.disposed) {
        // dispose() 後に await が完了して再登録されたぶんを解放する
        this.disposeFaceTextures()
        matTexture.dispose()
        return
      }
      this.matMaterial.map = matTexture
      this.matMaterial.color.set('#ffffff')
      this.matMaterial.needsUpdate = true
      for (const [boxId, entry] of this.boxes) this.applyFaceTextures(boxId, entry.materials)
    } catch (err) {
      // タグ資産が無くても色分けのみで動作継続する(仮テクスチャの縮退)
      console.warn('tag textures unavailable, falling back to flat colors:', err)
    }
  }

  private matMaterial = new THREE.MeshLambertMaterial({ color: '#10240f' })

  private buildMat(): void {
    const geometry = new THREE.PlaneGeometry(MAT_SIZE_MM.x, MAT_SIZE_MM.y)
    const mat = new THREE.Mesh(geometry, this.matMaterial)
    mat.rotation.x = -Math.PI / 2 // マットをxz平面(床)に寝かせる
    this.scene.add(mat)

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(4000, 4000),
      new THREE.MeshLambertMaterial({ color: '#030803' }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.y = -1
    this.scene.add(floor)
  }
}

const _up = new THREE.Vector3()
