// ディスプレイのシェル。3D盤面(BoardCanvas)の上に画面UI(ScreenView)と
// CRTオーバーレイを重ねる。高頻度の boxes は React を介さず BoardScene へ直接流す。
// デバッグHUDは ?hud を付けたときのみ表示(開発用)。

import { useEffect, useReducer, useRef, useState } from 'react'
import { bgm } from '../bgm/engine'
import { bgmTrackForScreen } from '../bgm/screenBgm'
import type { DisplayMessage } from '../contracts/ws'
import type { BoardScene } from '../three/BoardScene'
import { BoardCanvas } from '../three/BoardCanvas'
import { t } from '../i18n/strings'
import { deriveDisplaySfx } from '../sfx/displaySfx'
import { sfx } from '../sfx/engine'
import { ScreenView } from './screens/ScreenView'
import { DisplaySocket } from './socket'
import { initialDisplayState, reduceDisplay } from './store'
import './ui/retro.css'

export function DisplayApp() {
  const [state, dispatch] = useReducer(reduceDisplay, initialDisplayState)
  const [connected, setConnected] = useState(false)
  const [fps, setFps] = useState(0)
  const sceneRef = useRef<BoardScene | null>(null)
  // 効果音導出用の直前状態。React の描画バッチに依存せずメッセージ単位で
  // prev → next を追うため、リデューサをここでも畳み込む(純関数なので同値)
  const sfxStateRef = useRef(initialDisplayState)
  const showHud = new URLSearchParams(location.search).has('hud')

  // AudioContext の遅延アンロック(§5.12: Mac での初回クリック/キー操作)。
  useEffect(() => {
    const uninstallSfx = sfx.install()
    const uninstallBgm = bgm.install()
    return () => {
      uninstallBgm()
      uninstallSfx()
    }
  }, [])

  const bgmTrack = bgmTrackForScreen(state.screen?.screen ?? null)
  useEffect(() => bgm.setTrack(bgmTrack), [bgmTrack])

  useEffect(() => {
    const socket = new DisplaySocket({
      onMessage: (msg: DisplayMessage) => {
        // 高頻度の boxes は React を介さず直接3Dシーンへ
        if (msg.type === 'boxes') {
          sceneRef.current?.setBoxes(msg.payload.boxes)
          return
        }
        for (const e of deriveDisplaySfx(sfxStateRef.current, msg)) sfx.play(e.id, e)
        sfxStateRef.current = reduceDisplay(sfxStateRef.current, msg)
        dispatch(msg)
      },
      onStatus: setConnected,
    })
    return () => socket.close()
  }, [])

  const board = state.board
  return (
    <div className="retro-root" style={{ background: 'var(--crt-bg)' }}>
      <BoardCanvas onScene={(scene) => (sceneRef.current = scene)} onFps={setFps} />
      <ScreenView lang={state.lang} screen={state.screen} lastJudge={state.lastJudge} />
      {!connected && state.screen !== null && (
        <div className="retro-disconnected">{t(state.lang, 'disconnected')}</div>
      )}
      <div className="retro-scanlines" />
      {showHud && (
        <div
          style={{
            position: 'absolute',
            bottom: 8,
            left: 8,
            zIndex: 110,
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
      )}
    </div>
  )
}
