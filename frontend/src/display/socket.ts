// WebSocket接続の共通実装。切断時は指数バックオフで自動再接続する。
// 再接続直後はサーバーが snapshot を送るので、クライアント側の復元処理は不要
// (ws-messages.md: クライアントは常に snapshot で全状態を上書きできること)。
// /ws/display(受信専用)と /ws/controller(送受信)の両方で使う。

import type { ControllerMessage, ControllerToServerMessage, DisplayMessage } from '../contracts/ws'

const RECONNECT_MIN_MS = 500
const RECONNECT_MAX_MS = 5000
const STABLE_CONNECTION_MS = 3000

export interface SocketHandlers<TIn> {
  onMessage: (msg: TIn) => void
  onStatus?: (connected: boolean) => void
}

function wsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

export function defaultDisplayWsUrl(): string {
  return wsUrl('/ws/display')
}

export function defaultControllerWsUrl(): string {
  return wsUrl('/ws/controller')
}

export class ReconnectingSocket<TIn, TOut = never> {
  private ws: WebSocket | null = null
  private retryMs = RECONNECT_MIN_MS
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private closed = false

  private handlers: SocketHandlers<TIn>
  private url: string

  constructor(handlers: SocketHandlers<TIn>, url: string) {
    this.handlers = handlers
    this.url = url
    this.connect()
  }

  /** 接続中のみ送信する(切断中は破棄。ボタン等は再接続後の押し直しでよい) */
  send(msg: TOut): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  close(): void {
    this.closed = true
    if (this.retryTimer !== null) clearTimeout(this.retryTimer)
    const ws = this.ws
    this.ws = null
    if (!ws) return
    // 破棄後にハンドラが呼ばれないようにしてから閉じる
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null
    if (ws.readyState === WebSocket.CONNECTING) {
      // 接続確立前に close すると警告が出るため(StrictModeの二重マウント)、確立後に閉じる
      ws.onopen = () => ws.close()
    } else {
      ws.onopen = null
      ws.close()
    }
  }

  private connect(): void {
    if (this.closed) return
    const ws = new WebSocket(this.url)
    this.ws = ws
    let openedAt: number | null = null
    ws.onopen = () => {
      openedAt = performance.now()
      this.handlers.onStatus?.(true)
    }
    ws.onmessage = (event) => {
      let msg: TIn
      try {
        msg = JSON.parse(event.data as string) as TIn
      } catch {
        return // 壊れたフレームは無視
      }
      this.handlers.onMessage(msg)
    }
    ws.onclose = () => {
      if (this.ws !== ws) return
      // 一定時間安定して接続できていた場合のみバックオフをリセットする
      // (接続直後に切られ続けるケースで500ms連打にならないように)
      if (openedAt !== null && performance.now() - openedAt >= STABLE_CONNECTION_MS) {
        this.retryMs = RECONNECT_MIN_MS
      }
      this.handlers.onStatus?.(false)
      this.scheduleReconnect()
    }
    ws.onerror = () => ws.close()
  }

  private scheduleReconnect(): void {
    if (this.closed) return
    this.retryTimer = setTimeout(() => this.connect(), this.retryMs)
    this.retryMs = Math.min(this.retryMs * 2, RECONNECT_MAX_MS)
  }
}

export class DisplaySocket extends ReconnectingSocket<DisplayMessage> {
  constructor(handlers: SocketHandlers<DisplayMessage>, url: string = defaultDisplayWsUrl()) {
    super(handlers, url)
  }
}

export class ControllerSocket extends ReconnectingSocket<
  ControllerMessage,
  ControllerToServerMessage
> {
  constructor(handlers: SocketHandlers<ControllerMessage>, url: string = defaultControllerWsUrl()) {
    super(handlers, url)
  }
}
