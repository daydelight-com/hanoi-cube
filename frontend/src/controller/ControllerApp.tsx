// iPadコントローラ(仕様§6)。常時「← / 決定 / →」の3ボタンのみ。
// 例外はリザルトの名前入力時(input_mode=name)で、テキストフィールド+
// ソフトウェアキーボードを表示する。ボタンの意味づけはサーバーの状態機械が解釈する。
// 開発用に物理キーボード(←/→/Enter)でも操作できる。

import { useEffect, useReducer, useRef, useState } from 'react'
import type { ButtonName, ControllerMessage } from '../contracts/ws'
import { t } from '../i18n/strings'
import { ControllerSocket } from '../display/socket'
import { deriveControllerSfx } from '../sfx/controllerSfx'
import { sfx } from '../sfx/engine'
import { clampName, initialControllerState, nameToRestore, reduceController } from './store'
import './controller.css'

export function ControllerApp() {
  const [state, dispatch] = useReducer(reduceController, initialControllerState)
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<ControllerSocket | null>(null)
  // 切断中のローカル編集を再接続 snapshot 後に復元・再送するための最終入力値
  const lastTypedRef = useRef<string | null>(null)

  // AudioContext の遅延アンロック(§5.12: セッション開始時の初回タッチ)
  useEffect(() => sfx.install(), [])

  useEffect(() => {
    const socket = new ControllerSocket({
      onMessage: (msg: ControllerMessage) => {
        for (const id of deriveControllerSfx(msg)) sfx.play(id)
        dispatch(msg)
        if (msg.type === 'input_mode') lastTypedRef.current = null
        const restore = nameToRestore(msg, lastTypedRef.current)
        if (restore !== null) {
          dispatch({ type: 'type_name', text: restore })
          socketRef.current?.send({ type: 'name_text', payload: { text: restore } })
        }
      },
      onStatus: setConnected,
    })
    socketRef.current = socket
    return () => {
      socketRef.current = null
      socket.close()
    }
  }, [])

  // 誤操作対策(仕様§6): ピンチズームを抑止する(touch-action だけでは
  // Safari のジェスチャーを止められないため gesturestart も抑える)
  useEffect(() => {
    const prevent = (e: Event) => e.preventDefault()
    document.addEventListener('gesturestart', prevent)
    return () => document.removeEventListener('gesturestart', prevent)
  }, [])

  const sendButton = (button: ButtonName) => {
    // pad_button は押下ローカル再生(ws-messages.md §4・§5 注記)
    sfx.play('pad_button')
    socketRef.current?.send({ type: 'button', payload: { button } })
  }

  const nameMode = state.inputMode === 'name'

  // 開発用の物理キーボード操作(←/→/Enter)。名前入力中は入力欄に任せる
  useEffect(() => {
    if (nameMode) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat) return
      const button =
        e.key === 'ArrowLeft'
          ? 'left'
          : e.key === 'ArrowRight'
            ? 'right'
            : e.key === 'Enter'
              ? 'enter'
              : null
      if (button === null) return
      e.preventDefault()
      sendButton(button)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [nameMode])

  return (
    <div className="pad-root">
      {state.flash !== null && (
        // key=count で連続判定でもフラッシュを再トリガーする(§6: 振動の代替演出)
        <div key={state.flash.count} className={`pad-flash pad-flash--${state.flash.result}`} />
      )}
      {nameMode ? (
        <NameInput
          lang={state.lang}
          nameText={state.nameText}
          onType={(text) => {
            lastTypedRef.current = text
            dispatch({ type: 'type_name', text })
            socketRef.current?.send({ type: 'name_text', payload: { text: clampName(text) } })
          }}
          onDone={() => {
            sfx.play('pad_button')
            socketRef.current?.send({ type: 'name_done', payload: {} })
          }}
        />
      ) : (
        <div className="pad-buttons">
          {/* 矢印2つを左に並べ、その右に決定ボタンを置く */}
          <div className="pad-arrows">
            <PadButton className="pad-button--arrow" onPress={() => sendButton('left')}>
              ◀
            </PadButton>
            <PadButton className="pad-button--arrow" onPress={() => sendButton('right')}>
              ▶
            </PadButton>
          </div>
          <PadButton className="pad-button--enter" onPress={() => sendButton('enter')}>
            OK
          </PadButton>
        </div>
      )}
      {!connected && state.screen !== null && (
        <div className="pad-disconnected">{t(state.lang, 'disconnected')}</div>
      )}
      {!connected && state.screen === null && (
        <div className="pad-disconnected">{t(state.lang, 'connecting')}</div>
      )}
    </div>
  )
}

function PadButton({
  className,
  onPress,
  children,
}: {
  className: string
  onPress: () => void
  children: React.ReactNode
}) {
  const [pressed, setPressed] = useState(false)
  return (
    <button
      type="button"
      className={`pad-button ${className}${pressed ? ' pressed' : ''}`}
      // click ではなく pointerdown で即時送信(タッチの体感遅延を減らす)
      onPointerDown={(e) => {
        e.preventDefault()
        setPressed(true)
        onPress()
      }}
      onPointerUp={() => setPressed(false)}
      onPointerLeave={() => setPressed(false)}
      onPointerCancel={() => setPressed(false)}
    >
      {children}
    </button>
  )
}

function NameInput({
  lang,
  nameText,
  onType,
  onDone,
}: {
  lang: 'ja' | 'en'
  nameText: string
  onType: (text: string) => void
  onDone: () => void
}) {
  return (
    <form
      className="pad-name"
      // iOSソフトウェアキーボードの「開く」(改行/go)でも完了扱いにする
      onSubmit={(e) => {
        e.preventDefault()
        onDone()
      }}
    >
      <input
        className="pad-name-input"
        // リザルト入場時に自動でキーボードを出す(iOS Safariでは開かない場合が
        // あるため、フィールドタップでも開ける)
        autoFocus
        value={nameText}
        maxLength={10}
        placeholder={t(lang, 'padNamePlaceholder')}
        autoComplete="off"
        autoCorrect="off"
        enterKeyHint="done"
        onChange={(e) => onType(e.target.value)}
      />
      <button type="submit" className="pad-button pad-button--done">
        {t(lang, 'padNameDone')}
      </button>
    </form>
  )
}
