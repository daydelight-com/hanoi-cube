// BoardScene の React ラッパー。boxes ストリーム(30fps)は React の再レンダーを
// 経由せず onScene で得たハンドルへ直接流す(60fps描画のため)。

import { useEffect, useRef } from 'react'
import { BoardScene } from './BoardScene'

interface Props {
  onScene: (scene: BoardScene | null) => void
  onFps?: (fps: number) => void
}

export function BoardCanvas({ onScene, onFps }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const onSceneRef = useRef(onScene)
  const onFpsRef = useRef(onFps)
  useEffect(() => {
    onSceneRef.current = onScene
    onFpsRef.current = onFps
  })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const scene = new BoardScene(canvas)
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
      observer.disconnect()
      scene.dispose()
    }
  }, [])

  return <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
}
