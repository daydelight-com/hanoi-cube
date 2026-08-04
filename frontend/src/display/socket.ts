// /ws/display への接続。切断時は指数バックオフで自動再接続する。
// 再接続直後はサーバーが snapshot を送るので、クライアント側の復元処理は不要
// (ws-messages.md: クライアントは常に snapshot で全状態を上書きできること)。

import type { DisplayMessage } from '../contracts/ws'

const RECONNECT_MIN_MS = 500
const RECONNECT_MAX_MS = 5000
const STABLE_CONNECTION_MS = 3000

export interface DisplaySocketHandlers {
  onMessage: (msg: DisplayMessage) => void
  onStatus?: (connected: boolean) => void
}

export function defaultDisplayWsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/display`
}

export class DisplaySocket {
  private ws: WebSocket | null = null
  private retryMs = RECONNECT_MIN_MS
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private closed = false

  private handlers: DisplaySocketHandlers
  private url: string

  constructor(handlers: DisplaySocketHandlers, url: string = defaultDisplayWsUrl()) {
    this.handlers = handlers
    this.url = url
    this.connect()
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
      let msg: DisplayMessage
      try {
        msg = JSON.parse(event.data as string) as DisplayMessage
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
