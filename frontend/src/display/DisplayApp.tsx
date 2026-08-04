// ディスプレイ画面のシェル(S3: 3D盤面+デバッグHUD)。
// 画面ごとのUI(タイトル・ランキング等)は S4 で載せる。

import { useEffect, useReducer, useRef, useState } from 'react'
import type { DisplayMessage } from '../contracts/ws'
import type { BoardScene } from '../three/BoardScene'
import { BoardCanvas } from '../three/BoardCanvas'
import { DisplaySocket } from './socket'
import { initialDisplayState, reduceDisplay } from './store'

export function DisplayApp() {
  const [state, dispatch] = useReducer(reduceDisplay, initialDisplayState)
  const [connected, setConnected] = useState(false)
  const [fps, setFps] = useState(0)
  const sceneRef = useRef<BoardScene | null>(null)

  useEffect(() => {
    const socket = new DisplaySocket({
      onMessage: (msg: DisplayMessage) => {
        // 高頻度の boxes は React を介さず直接3Dシーンへ
        if (msg.type === 'boxes') {
          sceneRef.current?.setBoxes(msg.payload.boxes)
          return
        }
        dispatch(msg)
      },
      onStatus: setConnected,
    })
    return () => socket.close()
  }, [])

  const board = state.board
  return (
    <div style={{ position: 'fixed', inset: 0, background: '#060d06' }}>
      <BoardCanvas onScene={(scene) => (sceneRef.current = scene)} onFps={setFps} />
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          padding: '6px 10px',
          fontFamily: 'monospace',
          fontSize: 13,
          color: '#7ee06a',
          background: 'rgba(0, 0, 0, 0.55)',
          borderRadius: 4,
          whiteSpace: 'pre-line',
        }}
      >
        {[
          `ws: ${connected ? 'connected' : 'disconnected'}  fps: ${fps.toFixed(0)}`,
          `screen: ${state.screen?.screen ?? '-'}  lang: ${state.lang}`,
          board
            ? `board: ${board.board || '//'}  legal: ${board.legal}` +
              (board.violations.length
                ? `  violations: ${board.violations.map((v) => `${v.tower}:${v.type}`).join(', ')}`
                : '')
            : 'board: (未確定)',
          board ? `staging: ${board.staging_box_ids.join(', ') || '-'}` : '',
        ]
          .filter(Boolean)
          .join('\n')}
      </div>
    </div>
  )
}
