// BoardScene の React ラッパー。boxes ストリーム(30fps)は React の再レンダーを
// 経由せず onScene で得たハンドルへ直接流す(60fps描画のため)。

import { useEffect, useRef } from 'react'
import type { CameraSide } from '../contracts/ws'
import { BoardScene } from './BoardScene'

interface Props {
  onScene: (scene: BoardScene | null) => void
  onFps?: (fps: number) => void
  /** カメラの設置側(既定 back)。front のとき3D視点を180°反転する */
  cameraSide?: CameraSide
}

export function BoardCanvas({ onScene, onFps, cameraSide = 'back' }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<BoardScene | null>(null)
  const onSceneRef = useRef(onScene)
  const onFpsRef = useRef(onFps)
  const cameraSideRef = useRef(cameraSide)
  useEffect(() => {
    onSceneRef.current = onScene
    onFpsRef.current = onFps
    cameraSideRef.current = cameraSide
  })

  // snapshot がマウント後に届いた場合の追従(マウント時は下の effect が適用する)
  useEffect(() => {
    sceneRef.current?.setCameraSide(cameraSide)
  }, [cameraSide])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const scene = new BoardScene(canvas)
    sceneRef.current = scene
    scene.setCameraSide(cameraSideRef.current)
    scene.onFps = (fps) => onFpsRef.current?.(fps)

    const parent = canvas.parentElement
    const resize = () => {
      if (parent) scene.setSize(parent.clientWidth, parent.clientHeight)
    }
    resize()
    const observer = new ResizeObserver(resize)
    if (parent) observer.observe(parent)

    onSceneRef.current(scene)
    return () => {
      onSceneRef.current(null)
      sceneRef.current = null
      observer.disconnect()
      scene.dispose()
    }
  }, [])

  return <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
}
