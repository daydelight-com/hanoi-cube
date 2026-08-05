// Web Audio 効果音エンジン(仕様§5.12)。音源ファイルを使わず、矩形波・三角波の
// オシレーター+ゲインエンベロープ、打撃系はノイズバッファでリアルタイム合成する
// (ファミコン風チップチューン)。
//
// iOS/Safari 制約: AudioContext は初回ユーザー操作まで再生できないため、
// install() で pointerdown / keydown による遅延アンロックを仕込む
// (iPad はセッション開始時の初回タッチ、ディスプレイは Mac での初回クリック)。
//
// play() は AudioContext の有無に関わらず発火ログ(playedIds)へ記録する。
// 無人 E2E では音声出力を検証できないため、このログを window.__sfxPlayed 経由で
// 読んで発火の有無を代替検証する(e2e/full-play.mjs)。

import type { SfxId } from '../contracts/ws'

export interface PlayOpts {
  /** judge_success の獲得点。大きいほどアルペジオを豪華にする */
  points?: number
}

const MASTER_GAIN = 0.22
const PLAYED_LOG_MAX = 500

/** オシレーター1音(ゲインは指数減衰) */
function tone(
  ctx: AudioContext,
  out: AudioNode,
  freq: number,
  start: number,
  dur: number,
  opts: { type?: OscillatorType; gain?: number; slideTo?: number } = {},
): void {
  const osc = ctx.createOscillator()
  osc.type = opts.type ?? 'square'
  osc.frequency.setValueAtTime(freq, start)
  if (opts.slideTo !== undefined) {
    osc.frequency.exponentialRampToValueAtTime(Math.max(1, opts.slideTo), start + dur)
  }
  const g = ctx.createGain()
  g.gain.setValueAtTime(opts.gain ?? 1, start)
  g.gain.exponentialRampToValueAtTime(0.001, start + dur)
  osc.connect(g)
  g.connect(out)
  osc.start(start)
  osc.stop(start + dur + 0.02)
}

/** ホワイトノイズ1発(打撃系。lowpass で質感を変える) */
function noise(
  ctx: AudioContext,
  out: AudioNode,
  start: number,
  dur: number,
  opts: { gain?: number; lowpass?: number } = {},
): void {
  const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * dur) + 1, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1
  const src = ctx.createBufferSource()
  src.buffer = buffer
  const g = ctx.createGain()
  g.gain.setValueAtTime(opts.gain ?? 1, start)
  g.gain.exponentialRampToValueAtTime(0.001, start + dur)
  if (opts.lowpass !== undefined) {
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = opts.lowpass
    src.connect(filter)
    filter.connect(g)
  } else {
    src.connect(g)
  }
  g.connect(out)
  src.start(start)
}

/** 判定成功のアルペジオ音数(得点に応じて4〜8音。§5.12「得点に応じて豪華に」) */
export function successNoteCount(points: number): number {
  return Math.min(8, 4 + Math.floor(Math.max(0, points) / 10))
}

type Renderer = (ctx: AudioContext, out: AudioNode, t: number, opts: PlayOpts) => void

// ド=C5基準のアルペジオ(C E G C)。i//4 でオクターブを上げる
const ARPEGGIO = [523, 659, 784, 1047]

const RENDERERS: Record<SfxId, Renderer> = {
  cursor: (ctx, out, t) => tone(ctx, out, 880, t, 0.045, { gain: 0.7 }),
  decide: (ctx, out, t) => {
    tone(ctx, out, 660, t, 0.055)
    tone(ctx, out, 990, t + 0.06, 0.1)
  },
  back: (ctx, out, t) => {
    tone(ctx, out, 660, t, 0.055)
    tone(ctx, out, 440, t + 0.06, 0.1)
  },
  count: (ctx, out, t) => tone(ctx, out, 330, t, 0.16),
  go: (ctx, out, t) => {
    tone(ctx, out, 660, t, 0.5)
    tone(ctx, out, 880, t, 0.5, { type: 'triangle', gain: 0.8 })
  },
  judge_success: (ctx, out, t, opts) => {
    const n = successNoteCount(opts.points ?? 0)
    for (let i = 0; i < n; i += 1) {
      const freq = ARPEGGIO[i % 4] * 2 ** Math.floor(i / 4)
      tone(ctx, out, freq, t + i * 0.06, 0.08)
    }
    // コイン音(B5 → E6 サスティン)
    const coinAt = t + n * 0.06 + 0.02
    tone(ctx, out, 988, coinAt, 0.06, { gain: 0.9 })
    tone(ctx, out, 1319, coinAt + 0.06, 0.35, { gain: 0.9 })
  },
  judge_fail: (ctx, out, t) => {
    // 低い不協和音(短2度でうなり)のブザー
    tone(ctx, out, 110, t, 0.45, { gain: 0.9 })
    tone(ctx, out, 117, t, 0.45, { gain: 0.9 })
  },
  judge_dup: (ctx, out, t) => {
    tone(ctx, out, 550, t, 0.05, { gain: 0.8 })
    tone(ctx, out, 550, t + 0.1, 0.05, { gain: 0.8 })
  },
  tick10: (ctx, out, t) => tone(ctx, out, 1100, t, 0.035, { gain: 0.8 }),
  timeup: (ctx, out, t) => {
    // ゴング風: 低音の下降スイープ+アタックのノイズ
    tone(ctx, out, 196, t, 1.0, { slideTo: 98, gain: 0.9 })
    tone(ctx, out, 294, t, 0.7, { type: 'triangle', slideTo: 147, gain: 0.7 })
    noise(ctx, out, t, 0.12, { gain: 0.5, lowpass: 900 })
  },
  rank_tick: (ctx, out, t) => tone(ctx, out, 760, t, 0.03, { gain: 0.55 }),
  fanfare: (ctx, out, t) => {
    const steps: [number, number, number][] = [
      // [freq, offset, dur] タッタッタッターのファンファーレ+和音
      [523, 0, 0.09],
      [659, 0.1, 0.09],
      [784, 0.2, 0.09],
      [1047, 0.3, 0.45],
      [784, 0.3, 0.45],
      [659, 0.3, 0.45],
    ]
    for (const [freq, offset, dur] of steps) tone(ctx, out, freq, t + offset, dur, { gain: 0.8 })
  },
  key_touch: (ctx, out, t) => noise(ctx, out, t, 0.025, { gain: 0.5, lowpass: 4000 }),
  pad_button: (ctx, out, t) => {
    tone(ctx, out, 520, t, 0.035, { gain: 0.8 })
    noise(ctx, out, t, 0.015, { gain: 0.35 })
  },
  pad_flash: (ctx, out, t) => {
    // 振動の代替(仕様§6): 強めのインパクト音
    noise(ctx, out, t, 0.25, { gain: 1, lowpass: 1200 })
    tone(ctx, out, 90, t, 0.3, { slideTo: 55, gain: 1 })
  },
}

export class SfxEngine {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  /** 発火ログ(音声出力の有無に関わらず記録。E2E・デバッグ用) */
  readonly playedIds: SfxId[] = []

  /**
   * 初回ユーザー操作での遅延アンロックを仕込む(§5.12 iOS/Safari 制約)。
   * リスナーは残し続け、suspend されても次の操作で resume する。
   */
  install(target: Pick<Window, 'addEventListener' | 'removeEventListener'> = window): () => void {
    const unlock = () => this.unlock()
    target.addEventListener('pointerdown', unlock, { passive: true })
    target.addEventListener('keydown', unlock)
    return () => {
      target.removeEventListener('pointerdown', unlock)
      target.removeEventListener('keydown', unlock)
    }
  }

  /** ユーザー操作ハンドラ内から呼ぶ。AudioContext を生成/再開する */
  unlock(): void {
    if (this.ctx === null) {
      if (typeof AudioContext === 'undefined') return
      this.ctx = new AudioContext()
      this.master = this.ctx.createGain()
      this.master.gain.value = MASTER_GAIN
      this.master.connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume()
  }

  play(id: SfxId, opts: PlayOpts = {}): void {
    // 型上は SfxId だが、サーバーの sfx メッセージ経由では実行時に未知のIDが
    // 届きうる(契約ドリフト対策)。未知IDは無視する
    if (!Object.hasOwn(RENDERERS, id)) return
    this.playedIds.push(id)
    if (this.playedIds.length > PLAYED_LOG_MAX) {
      this.playedIds.splice(0, this.playedIds.length - PLAYED_LOG_MAX)
    }
    const ctx = this.ctx
    if (ctx === null || ctx.state !== 'running' || this.master === null) return
    RENDERERS[id](ctx, this.master, ctx.currentTime + 0.01, opts)
  }
}

/** ディスプレイ・コントローラ共用のシングルトン(1ページに1App) */
export const sfx = new SfxEngine()

// 無人E2E・デバッグ用に発火ログとエンジン本体を公開する(音声そのものは
// 無人検証できないため。__sfx は実機でのスピーカーテストにも使える:
// コンソールで __sfx.unlock() 後に __sfx.play('fanfare') など)
declare global {
  interface Window {
    __sfxPlayed?: readonly SfxId[]
    __sfx?: SfxEngine
  }
}
if (typeof window !== 'undefined') {
  window.__sfxPlayed = sfx.playedIds
  window.__sfx = sfx
}
