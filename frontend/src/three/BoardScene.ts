// 3D盤面シーン: マット+箱9個。CvFrame の boxes(約30fps)を目標値として受け取り、
// 描画ループ(60fps)で指数平滑化しながら追従させる。React には依存しない。

import * as THREE from 'three'
import type { BoxObservation, BoxId, BoxSize } from '../contracts/cv'
import { BOX_EDGE_MM } from '../contracts/cv'
import type { CameraSide } from '../contracts/ws'
import { FACE_BY_MATERIAL_INDEX } from './faces'
import {
  MAT_SIZE_MM,
  STAGING_Y_MM,
  TOWER_X_MM,
  TOWER_Y_MM,
  matPosToThree,
  matQuatToThree,
} from './layout'
import { nextGroundOffsetMm } from './groundOffset'
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

interface SceneInteractions {
  onBoxClick: (boxId: BoxId) => void
  onTowerClick: (tower: 'A' | 'B' | 'C') => void
}

export class BoardScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private sun: THREE.DirectionalLight
  private lastTickMs: number | null = null
  private boxes = new Map<BoxId, BoxEntry>()
  // 接地補正量(mm)。groundOffset.ts 参照。可視箱の描画高さにだけ足す
  private groundOffsetMm = 0
  private faceTextures = new Map<BoxId, Map<number, THREE.Texture>>()
  private disposed = false
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private towerTargets: THREE.Mesh[] = []
  private interactions: SceneInteractions | null = null
  private selectedBoxId: BoxId | null = null
  private selectionOutline: THREE.LineSegments

  // FPS計測(直近1秒の描画フレーム数)。DoD確認用に HUD へ通知する
  private frameCount = 0
  private fpsWindowStart = 0
  onFps: ((fps: number) => void) | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

    this.camera = new THREE.PerspectiveCamera(45, 1, 10, 5000)
    this.scene.background = new THREE.Color('#060d06')
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.9))
    this.sun = new THREE.DirectionalLight(0xffffff, 1.6)
    this.scene.add(this.sun)
    this.setCameraSide('back')

    this.buildMat()
    this.selectionOutline = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)),
      new THREE.LineBasicMaterial({ color: '#fff2a8' }),
    )
    this.selectionOutline.visible = false
    this.scene.add(this.selectionOutline)
    canvas.addEventListener('pointerdown', this.onPointerDown)
    void this.loadTextures()
    this.renderer.setAnimationLoop(() => this.tick())
  }

  /**
   * 視点をカメラ設置側から決める(ws-messages.md §3)。back=待機エリア側(+z)からの
   * 既定視点。front=カメラが待機エリア側にある設営で、プレイヤーは反対側にいるため
   * 塔側(-z)から見た視点に180°反転する。座標データは変換しない(視点だけ変える)。
   */
  setCameraSide(side: CameraSide): void {
    const sign = side === 'front' ? -1 : 1
    // カメラ距離は幅600mmマット時の値をマット幅に比例させ、寸法によらず同じ画角比で映す
    const camScale = MAT_SIZE_MM.x / 600
    this.camera.position.set(0, 520 * camScale, sign * 640 * camScale)
    this.camera.lookAt(0, 40 * camScale, 0)
    // 反転視点でも「向かって左・手前上方からの光」に見えるよう x/z とも反転する
    this.sun.position.set(sign * -250, 600, sign * 400)
  }

  /** 最新フレームの箱位置を目標値として設定する(WSの boxes メッセージから呼ぶ) */
  setBoxes(boxes: BoxObservation[]): void {
    this.groundOffsetMm = nextGroundOffsetMm(this.groundOffsetMm, boxes)
    for (const obs of boxes) {
      const entry = this.ensureBox(obs.box_id, obs.size)
      const edge = BOX_EDGE_MM[obs.size]
      const t = entry.target
      matPosToThree(obs.pos_mm, t.center)
      matQuatToThree(obs.quat, t.quat)
      // pos_mm はワールド座標の底面中心(ひっくり返しでも接地面側)。
      // ワールド上方向に半辺ぶん進めて箱中心にする(箱ローカル上方向ではない)
      t.center.add(_up.set(0, edge / 2, 0))
      // 接地補正は実測位置(可視)のみ。非可視の保持・プレースホルダ位置には掛けない
      if (obs.visible) t.center.y += this.groundOffsetMm
      t.visible = obs.visible
    }
  }

  setSize(width: number, height: number): void {
    this.renderer.setSize(width, height, false)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
  }

  setInteractions(interactions: SceneInteractions): void {
    this.interactions = interactions
  }

  setSelectedBox(boxId: BoxId | null): void {
    this.selectedBoxId = boxId
  }

  dispose(): void {
    this.disposed = true
    this.renderer.domElement.removeEventListener('pointerdown', this.onPointerDown)
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
    this.updateSelectionOutline()
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
    mesh.userData.boxId = boxId
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

    for (const tower of ['A', 'B', 'C'] as const) {
      const position = new THREE.Vector3()
      matPosToThree([TOWER_X_MM[tower], TOWER_Y_MM, 0], position)
      const target = new THREE.Mesh(
        new THREE.CircleGeometry(MAT_SIZE_MM.x / 10, 24),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
      )
      target.rotation.x = -Math.PI / 2
      target.position.copy(position)
      target.position.y = 0.5
      target.userData.tower = tower
      this.towerTargets.push(target)
      this.scene.add(target)
    }
  }

  private onPointerDown = (event: PointerEvent): void => {
    if (!this.interactions) return
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    )
    this.raycaster.setFromCamera(this.pointer, this.camera)

    const boxHits = this.raycaster.intersectObjects(
      [...this.boxes.values()].map((entry) => entry.mesh),
      false,
    )
    const boxId = boxHits[0]?.object.userData.boxId as BoxId | undefined
    if (boxId) {
      this.interactions.onBoxClick(boxId)
      return
    }
    const towerHits = this.raycaster.intersectObjects(this.towerTargets, false)
    const tower = towerHits[0]?.object.userData.tower as 'A' | 'B' | 'C' | undefined
    if (tower) this.interactions.onTowerClick(tower)
  }

  private updateSelectionOutline(): void {
    const selected = this.selectedBoxId === null ? undefined : this.boxes.get(this.selectedBoxId)
    if (!selected) {
      this.selectionOutline.visible = false
      return
    }
    const edge = BOX_EDGE_MM[selected.size]
    this.selectionOutline.visible = true
    this.selectionOutline.position.copy(selected.mesh.position)
    this.selectionOutline.quaternion.copy(selected.mesh.quaternion)
    this.selectionOutline.scale.setScalar(edge * 1.08)
  }
}

const _up = new THREE.Vector3()
