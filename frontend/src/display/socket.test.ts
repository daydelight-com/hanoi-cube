// DisplaySocket / ControllerSocket の再接続・送信ロジックのテスト
// (S3 申し送り: ブラウザ実測のみだった部分)。
// WebSocket をフェイクに差し替え、フェイクタイマーで再接続バックオフを検証する。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DisplayMessage } from '../contracts/ws'
import { ControllerSocket, DisplaySocket } from './socket'

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: FakeWebSocket[] = []

  url: string
  readyState = FakeWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  closeCalls = 0
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  close(): void {
    this.closeCalls += 1
    this.readyState = FakeWebSocket.CLOSED
  }

  send(data: string): void {
    this.sent.push(data)
  }

  // ---- テスト用シミュレーション ----
  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  simulateMessage(data: string): void {
    this.onmessage?.({ data })
  }

  simulateClose(): void {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }

  // 実WebSocketは error の後に close イベントが続く
  simulateError(): void {
    this.onerror?.()
    if (this.closeCalls > 0) this.onclose?.()
  }
}

function lastWs(): FakeWebSocket {
  return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
}

describe('DisplaySocket', () => {
  let received: DisplayMessage[]
  let statuses: boolean[]

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    received = []
    statuses = []
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  function create(): DisplaySocket {
    return new DisplaySocket(
      { onMessage: (m) => received.push(m), onStatus: (c) => statuses.push(c) },
      'ws://test/ws/display',
    )
  }

  it('接続してJSONメッセージをパースして渡す(壊れたフレームは無視)', () => {
    const socket = create()
    expect(FakeWebSocket.instances).toHaveLength(1)
    lastWs().simulateOpen()
    expect(statuses).toEqual([true])

    lastWs().simulateMessage('{"type":"lang","payload":{"lang":"en"}}')
    lastWs().simulateMessage('not-json')
    expect(received).toEqual([{ type: 'lang', payload: { lang: 'en' } }])
    socket.close()
  })

  it('切断のたびに指数バックオフで再接続する(500→1000→2000、上限5000)', () => {
    const socket = create()
    const delays = [500, 1000, 2000, 4000, 5000, 5000]
    for (const delay of delays) {
      const count = FakeWebSocket.instances.length
      lastWs().simulateClose()
      vi.advanceTimersByTime(delay - 1)
      expect(FakeWebSocket.instances).toHaveLength(count)
      vi.advanceTimersByTime(1)
      expect(FakeWebSocket.instances).toHaveLength(count + 1)
    }
    socket.close()
  })

  it('3秒以上安定した接続の後はバックオフがリセットされる', () => {
    const socket = create()
    // 2回失敗してバックオフを2000msまで進める
    lastWs().simulateClose()
    vi.advanceTimersByTime(500)
    lastWs().simulateClose()
    vi.advanceTimersByTime(1000)

    // 安定した接続(3秒以上)ののち切断 → 次の再接続は最小値500msに戻る
    lastWs().simulateOpen()
    vi.advanceTimersByTime(3000)
    const count = FakeWebSocket.instances.length
    lastWs().simulateClose()
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances).toHaveLength(count + 1)
    socket.close()
  })

  it('接続直後に切られ続けてもバックオフはリセットされない', () => {
    const socket = create()
    lastWs().simulateClose()
    vi.advanceTimersByTime(500)
    // 開いてすぐ(3秒未満)切断される
    lastWs().simulateOpen()
    vi.advanceTimersByTime(1000)
    const count = FakeWebSocket.instances.length
    lastWs().simulateClose()
    // 500msでは再接続せず、倍化した1000msで再接続する
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances).toHaveLength(count)
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances).toHaveLength(count + 1)
    socket.close()
  })

  it('onerror 経由でも切断扱いになり再接続する', () => {
    const socket = create()
    lastWs().simulateOpen()
    lastWs().simulateError() // 実装は onerror で ws.close() → 続く onclose で再接続予約
    expect(statuses).toEqual([true, false])
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances).toHaveLength(2)
    socket.close()
  })

  it('close() 後は再接続もハンドラ呼び出しもしない', () => {
    const socket = create()
    const ws = lastWs()
    ws.simulateOpen()
    socket.close()
    expect(ws.closeCalls).toBe(1)
    expect(ws.onmessage).toBeNull()
    expect(ws.onclose).toBeNull()
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(statuses).toEqual([true])
  })

  it('CONNECTING 中の close() は接続確立後に閉じる(StrictMode二重マウント対策)', () => {
    const socket = create()
    const ws = lastWs()
    socket.close()
    expect(ws.closeCalls).toBe(0) // まだ閉じない
    ws.simulateOpen()
    expect(ws.closeCalls).toBe(1) // 確立後に閉じる
    expect(statuses).toEqual([]) // onStatus は呼ばれない
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})

describe('ControllerSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('location', { protocol: 'http:', host: 'test-host' })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('既定で /ws/controller に接続する(ws-messages.md §5)', () => {
    const socket = new ControllerSocket({ onMessage: () => {} })
    expect(lastWs().url).toBe('ws://test-host/ws/controller')
    socket.close()
  })

  it('OPEN 中の send はJSONで送信し、未接続中は破棄する', () => {
    const socket = new ControllerSocket({ onMessage: () => {} }, 'ws://test/ws/controller')
    const ws = lastWs()
    socket.send({ type: 'button', payload: { button: 'enter' } }) // CONNECTING 中は破棄
    expect(ws.sent).toEqual([])

    ws.simulateOpen()
    socket.send({ type: 'name_text', payload: { text: 'たろう' } })
    expect(ws.sent).toEqual(['{"type":"name_text","payload":{"text":"たろう"}}'])

    ws.simulateClose()
    socket.send({ type: 'button', payload: { button: 'left' } }) // 切断後は破棄
    expect(ws.sent).toHaveLength(1)
    socket.close()
  })
})
