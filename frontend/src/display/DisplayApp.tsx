// ディスプレイのシェル。3D盤面(BoardCanvas)の上に画面UI(ScreenView)と
// CRTオーバーレイを重ねる。高頻度の boxes は React を介さず BoardScene へ直接流す。
// デバッグHUDは ?hud を付けたときのみ表示(開発用)。

import { useEffect, useReducer, useRef, useState } from 'react'
import { bgm } from '../bgm/engine'
import { bgmTrackForScreen } from '../bgm/screenBgm'
import type { BoxId } from '../contracts/cv'
import type { ButtonName, DisplayMessage } from '../contracts/ws'
import type { BoardScene } from '../three/BoardScene'
import { BoardCanvas } from '../three/BoardCanvas'
import { t } from '../i18n/strings'
import { deriveDisplaySfx } from '../sfx/displaySfx'
import { sfx } from '../sfx/engine'
import { ScreenView } from './screens/ScreenView'
import { ControllerSocket, DisplaySocket } from './socket'
import { isSelectableBox, moveMockBox, towerForBox } from './boardInteraction'
import { focusedSelectionButtons, modeSelectionButtons } from './controls'
import { initialDisplayState, reduceDisplay } from './store'
import './ui/retro.css'

export function DisplayApp() {
  const [state, dispatch] = useReducer(reduceDisplay, initialDisplayState)
  const [connected, setConnected] = useState(false)
  const [fps, setFps] = useState(0)
  const [selectedBoxId, setSelectedBoxId] = useState<BoxId | null>(null)
  const sceneRef = useRef<BoardScene | null>(null)
  const controllerSocketRef = useRef<ControllerSocket | null>(null)
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

  // 表示画面からも既存のコントローラ用プロトコルで操作を送る。画面状態は
  // DisplaySocket の配信を正としているので、ここでは controller の snapshot を使わない。
  useEffect(() => {
    const socket = new ControllerSocket({ onMessage: () => {} })
    controllerSocketRef.current = socket
    return () => {
      controllerSocketRef.current = null
      socket.close()
    }
  }, [])

  const sendButtons = (buttons: ButtonName[]) => {
    for (const button of buttons) {
      controllerSocketRef.current?.send({ type: 'button', payload: { button } })
    }
  }

  // 表示上で「Enter」と案内している操作だけ、物理キーボードでも実行できるようにする。
  // ほかの画面への誤操作や長押し連打は防ぐ。
  useEffect(() => {
    const screen = state.screen?.screen
    if (
      screen !== 'practice' &&
      screen !== 'rule_dialog' &&
      screen !== 'ranking' &&
      screen !== 'qr'
    ) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat) return
      const button =
        event.key === 'Enter'
          ? 'enter'
          : screen === 'rule_dialog' && event.key === 'ArrowLeft'
            ? 'left'
            : screen === 'rule_dialog' && event.key === 'ArrowRight'
              ? 'right'
              : null
      if (button === null) return
      event.preventDefault()
      controllerSocketRef.current?.send({ type: 'button', payload: { button } })
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [state.screen?.screen])

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
        if (msg.type === 'board') setSelectedBoxId(null)
        for (const e of deriveDisplaySfx(sfxStateRef.current, msg)) sfx.play(e.id, e)
        sfxStateRef.current = reduceDisplay(sfxStateRef.current, msg)
        dispatch(msg)
      },
      onStatus: setConnected,
    })
    return () => socket.close()
  }, [])

  const board = state.board
  const boardInteractionEnabled =
    state.screen?.screen === 'practice' || state.screen?.screen === 'game_play'

  const moveSelectedBox = (tower: 'A' | 'B' | 'C') => {
    if (selectedBoxId === null) return
    void moveMockBox(selectedBoxId, tower)
      .then(() => setSelectedBoxId(null))
      // 実CV運用時など、モックAPIが使えない場合は選択を残して再試行できるようにする。
      .catch(() => undefined)
  }

  return (
    <div className="retro-root" style={{ background: 'var(--crt-bg)' }}>
      <BoardCanvas
        onScene={(scene) => (sceneRef.current = scene)}
        onFps={setFps}
        cameraSide={state.cameraSide}
        selectedBoxId={selectedBoxId}
        onBoxClick={(boxId) => {
          if (!boardInteractionEnabled) return
          // 選択済みなら、積まれている箱をクリックしても選び直さず、その塔を移動先にする。
          // これにより空塔と同じように、箱のある塔にもそのまま積める。
          if (selectedBoxId !== null) {
            const tower = towerForBox(board, boxId)
            if (tower !== null) {
              moveSelectedBox(tower)
              return
            }
          }
          if (isSelectableBox(board, boxId)) setSelectedBoxId(boxId)
        }}
        onTowerClick={(tower) => {
          if (boardInteractionEnabled) moveSelectedBox(tower)
        }}
      />
      <ScreenView
        lang={state.lang}
        screen={state.screen}
        lastJudge={state.lastJudge}
        onButton={(button) => sendButtons([button])}
        onModeSelect={(target) => {
          if (state.screen?.screen !== 'mode_select') return
          sendButtons(modeSelectionButtons(state.screen.ctx.focus, target))
        }}
        onPracticeSelect={(target) => {
          if (state.screen?.screen !== 'practice') return
          sendButtons(
            focusedSelectionButtons(state.screen.ctx.selection, target, (item) =>
              item === 'back' ? 'left' : 'right',
            ),
          )
        }}
        onResultSelect={(target) => {
          if (state.screen?.screen !== 'result' || state.screen.ctx.input_mode !== 'buttons') return
          sendButtons(
            focusedSelectionButtons(state.screen.ctx.focus, target, (item) =>
              item === 'input' ? 'left' : 'right',
            ),
          )
        }}
        onNameType={(text) => {
          controllerSocketRef.current?.send({
            type: 'name_text',
            payload: { text: text.slice(0, 10) },
          })
        }}
        onNameDone={() => controllerSocketRef.current?.send({ type: 'name_done', payload: {} })}
      />
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
            `screen: ${state.screen?.screen ?? '-'}  lang: ${state.lang}  camera: ${state.cameraSide}`,
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
