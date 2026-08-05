// Web Audio API で3曲のチップチューンをリアルタイム合成するBGMエンジン。
// 短い先読みスケジューラで16分音符を並べるため音源ファイルが不要で、
// 各曲の小節境界を正確にループできる。SFXとは別Gainで小さめにミックスする。

import { BGM_TRACKS, type BgmNote, type BgmTrack, type BgmTrackId, type BgmVoice } from './tracks'

const STEPS_PER_BAR = 16
const SCHEDULE_AHEAD_SECONDS = 0.14
const SCHEDULER_INTERVAL_MS = 30
// 各ボイス側と曲別Gainでも十分に減衰しているため、最終バスは0.78。
// 合成後のBGMピークはおよそ0.07〜0.08で、SFXマスター0.22より約9dB低い。
const MASTER_GAIN = 0.78
const SILENCE = 0.0001
const TRACK_FADE_OUT_SECONDS = 0.24

const FADE_IN_SECONDS: Record<BgmTrackId, number> = {
  waiting: 0.45,
  gameplay: 0.12,
  result: 0.7,
}

const START_DELAY_SECONDS: Record<BgmTrackId, number> = {
  waiting: 0.045,
  gameplay: 0.045,
  // 1秒のタイムアップゴングを主役にし、結果曲は少し遅れて立ち上げる。
  result: 0.45,
}

interface VoiceStyle {
  wave: OscillatorType
  gain: number
  attack: number
  release: number
  gate: number
}

const VOICES: Record<BgmTrackId, Record<BgmVoice, VoiceStyle>> = {
  waiting: {
    lead: { wave: 'square', gain: 0.14, attack: 0.008, release: 0.07, gate: 0.72 },
    arp: { wave: 'square', gain: 0.045, attack: 0.004, release: 0.035, gate: 0.52 },
    bass: { wave: 'triangle', gain: 0.19, attack: 0.008, release: 0.08, gate: 0.78 },
    pad: { wave: 'triangle', gain: 0.055, attack: 0.035, release: 0.16, gate: 0.92 },
  },
  gameplay: {
    lead: { wave: 'square', gain: 0.15, attack: 0.004, release: 0.045, gate: 0.78 },
    arp: { wave: 'square', gain: 0.052, attack: 0.003, release: 0.025, gate: 0.58 },
    bass: { wave: 'triangle', gain: 0.22, attack: 0.004, release: 0.05, gate: 0.86 },
    pad: { wave: 'sawtooth', gain: 0.025, attack: 0.018, release: 0.1, gate: 0.88 },
  },
  result: {
    lead: { wave: 'square', gain: 0.13, attack: 0.01, release: 0.095, gate: 0.76 },
    arp: { wave: 'square', gain: 0.038, attack: 0.005, release: 0.045, gate: 0.55 },
    bass: { wave: 'triangle', gain: 0.17, attack: 0.012, release: 0.1, gate: 0.82 },
    pad: { wave: 'triangle', gain: 0.065, attack: 0.045, release: 0.2, gate: 0.94 },
  },
}

interface TrackSession {
  id: BgmTrackId
  track: BgmTrack
  bus: GainNode
  filter: BiquadFilterNode
  eventsByStep: ReadonlyMap<number, readonly BgmNote[]>
  kickSteps: ReadonlySet<number>
  snareSteps: ReadonlySet<number>
  hatSteps: ReadonlySet<number>
  step: number
  nextStepAt: number
}

function midiFrequency(midi: number): number {
  return 440 * 2 ** ((midi - 69) / 12)
}

function secondsPerStep(track: BgmTrack): number {
  return 60 / track.bpm / 4
}

function groupEvents(notes: readonly BgmNote[]): ReadonlyMap<number, readonly BgmNote[]> {
  const grouped = new Map<number, BgmNote[]>()
  for (const note of notes) {
    const events = grouped.get(note.step)
    if (events === undefined) grouped.set(note.step, [note])
    else events.push(note)
  }
  return grouped
}

function setGainEnvelope(
  gain: AudioParam,
  start: number,
  peak: number,
  holdUntil: number,
  end: number,
  attack: number,
): void {
  gain.setValueAtTime(SILENCE, start)
  gain.exponentialRampToValueAtTime(Math.max(SILENCE, peak), start + attack)
  gain.setValueAtTime(Math.max(SILENCE, peak), Math.max(start + attack, holdUntil))
  gain.exponentialRampToValueAtTime(SILENCE, end)
}

export class BgmEngine {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private compressor: DynamicsCompressorNode | null = null
  private noiseBuffer: AudioBuffer | null = null
  private requested: BgmTrackId | null = null
  private session: TrackSession | null = null
  private schedulerTimer: ReturnType<typeof setTimeout> | null = null
  private scheduledNotes = 0

  /** 音声出力不可のE2Eでも画面→曲の切替を検証できる履歴。 */
  readonly trackHistory: Array<BgmTrackId | null> = []
  /** AudioContextが実際に起動し、演奏を開始した曲の履歴。 */
  readonly startedTracks: BgmTrackId[] = []

  get requestedTrack(): BgmTrackId | null {
    return this.requested
  }

  /** 実ブラウザE2E・設営時デバッグ用の読み取り専用状態。 */
  get playbackState(): {
    context: AudioContextState | 'locked'
    activeTrack: BgmTrackId | null
    scheduledNotes: number
    startedTracks: readonly BgmTrackId[]
  } {
    return {
      context: this.ctx?.state ?? 'locked',
      activeTrack: this.session?.id ?? null,
      scheduledNotes: this.scheduledNotes,
      startedTracks: this.startedTracks,
    }
  }

  /** 初回ユーザー操作でAudioContextを生成・再開する。 */
  install(target: Pick<Window, 'addEventListener' | 'removeEventListener'> = window): () => void {
    const unlock = () => this.unlock()
    target.addEventListener('pointerdown', unlock, { passive: true })
    target.addEventListener('keydown', unlock)
    return () => {
      target.removeEventListener('pointerdown', unlock)
      target.removeEventListener('keydown', unlock)
    }
  }

  unlock(): void {
    if (this.ctx === null) {
      if (typeof AudioContext === 'undefined') return
      this.ctx = new AudioContext()
      this.master = this.ctx.createGain()
      this.master.gain.value = MASTER_GAIN
      this.compressor = this.ctx.createDynamicsCompressor()
      this.compressor.threshold.value = -16
      this.compressor.knee.value = 10
      this.compressor.ratio.value = 4
      this.compressor.attack.value = 0.005
      this.compressor.release.value = 0.16
      this.master.connect(this.compressor)
      this.compressor.connect(this.ctx.destination)
    }

    const startRequestedTrack = () => {
      if (this.ctx?.state === 'running') this.switchTrack(this.requested)
    }
    if (this.ctx.state === 'suspended') {
      void this.ctx
        .resume()
        .then(startRequestedTrack)
        .catch(() => {})
    } else {
      startRequestedTrack()
    }
  }

  /** 同じIDの再指定は何もしないため、同一フェーズ内では曲が続く。 */
  setTrack(id: BgmTrackId | null): void {
    if (this.requested === id) return
    this.requested = id
    this.trackHistory.push(id)
    if (this.ctx?.state === 'running') this.switchTrack(id)
  }

  private switchTrack(id: BgmTrackId | null): void {
    const ctx = this.ctx
    const master = this.master
    if (ctx === null || master === null || ctx.state !== 'running') return
    if (this.session?.id === id) return

    const previous = this.session
    this.session = null
    if (previous !== null) {
      const now = ctx.currentTime
      previous.bus.gain.cancelAndHoldAtTime(now)
      previous.bus.gain.exponentialRampToValueAtTime(SILENCE, now + TRACK_FADE_OUT_SECONDS)
      setTimeout(
        () => {
          previous.bus.disconnect()
          previous.filter.disconnect()
        },
        (TRACK_FADE_OUT_SECONDS + 1.2) * 1000,
      )
    }

    if (id === null) {
      this.stopScheduler()
      return
    }

    const track = BGM_TRACKS[id]
    const bus = ctx.createGain()
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = id === 'gameplay' ? 6800 : 5600
    filter.Q.value = 0.35
    bus.connect(filter)
    filter.connect(master)

    const now = ctx.currentTime
    const startAt = now + START_DELAY_SECONDS[id]
    bus.gain.setValueAtTime(SILENCE, now)
    bus.gain.setValueAtTime(SILENCE, startAt)
    bus.gain.exponentialRampToValueAtTime(track.gain, startAt + FADE_IN_SECONDS[id])
    this.session = {
      id,
      track,
      bus,
      filter,
      eventsByStep: groupEvents(track.notes),
      kickSteps: new Set(track.drums.kick),
      snareSteps: new Set(track.drums.snare),
      hatSteps: new Set(track.drums.hat),
      step: 0,
      nextStepAt: startAt,
    }
    this.startedTracks.push(id)
    this.ensureScheduler()
    this.scheduleAhead()
  }

  private ensureScheduler(): void {
    if (this.schedulerTimer !== null) return
    const tick = () => {
      this.schedulerTimer = null
      this.scheduleAhead()
      if (this.session !== null) this.schedulerTimer = setTimeout(tick, SCHEDULER_INTERVAL_MS)
    }
    this.schedulerTimer = setTimeout(tick, SCHEDULER_INTERVAL_MS)
  }

  private stopScheduler(): void {
    if (this.schedulerTimer !== null) clearTimeout(this.schedulerTimer)
    this.schedulerTimer = null
  }

  private scheduleAhead(): void {
    const ctx = this.ctx
    const session = this.session
    if (ctx === null || session === null || ctx.state !== 'running') return

    const stepSeconds = secondsPerStep(session.track)
    // タブ停止などでスケジューラが遅れた場合、過去の全音を一気に鳴らさず現在位置へ追いつく。
    if (session.nextStepAt < ctx.currentTime - stepSeconds) {
      const missed = Math.floor((ctx.currentTime - session.nextStepAt) / stepSeconds)
      session.step = (session.step + missed) % (session.track.bars * STEPS_PER_BAR)
      session.nextStepAt += missed * stepSeconds
    }

    while (session.nextStepAt < ctx.currentTime + SCHEDULE_AHEAD_SECONDS) {
      this.scheduleStep(session, session.step, session.nextStepAt, stepSeconds)
      session.step = (session.step + 1) % (session.track.bars * STEPS_PER_BAR)
      session.nextStepAt += stepSeconds
    }
  }

  private scheduleStep(
    session: TrackSession,
    step: number,
    start: number,
    stepSeconds: number,
  ): void {
    for (const note of session.eventsByStep.get(step) ?? []) {
      this.scheduleNote(session, note, start, stepSeconds)
    }
    if (session.kickSteps.has(step)) this.scheduleKick(session.bus, start, session.id)
    if (session.snareSteps.has(step)) this.scheduleNoise(session.bus, start, 0.095, 0.055, 1700)
    if (session.hatSteps.has(step)) this.scheduleNoise(session.bus, start, 0.025, 0.018, 5200)
  }

  private scheduleNote(
    session: TrackSession,
    note: BgmNote,
    start: number,
    stepSeconds: number,
  ): void {
    const ctx = this.ctx
    if (ctx === null) return
    const style = VOICES[session.id][note.voice]
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const duration = Math.max(0.035, note.length * stepSeconds * style.gate)
    const release = Math.min(style.release, duration * 0.45)
    const end = start + duration
    osc.type = style.wave
    osc.frequency.setValueAtTime(midiFrequency(note.midi), start)
    // 本番リードだけ、ごく浅いデチューンで輪郭を強める。
    if (session.id === 'gameplay' && note.voice === 'lead') osc.detune.value = -3
    const velocity = Math.max(0.1, Math.min(1.4, note.velocity ?? 1))
    setGainEnvelope(
      gain.gain,
      start,
      style.gain * velocity,
      end - release,
      end,
      Math.min(style.attack, duration * 0.25),
    )
    osc.connect(gain)
    gain.connect(session.bus)
    osc.start(start)
    osc.stop(end + 0.025)
    this.scheduledNotes += 1
  }

  private scheduleKick(out: AudioNode, start: number, id: BgmTrackId): void {
    const ctx = this.ctx
    if (ctx === null) return
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const duration = id === 'gameplay' ? 0.12 : 0.1
    osc.type = 'sine'
    osc.frequency.setValueAtTime(id === 'gameplay' ? 145 : 120, start)
    osc.frequency.exponentialRampToValueAtTime(48, start + duration)
    gain.gain.setValueAtTime(id === 'gameplay' ? 0.16 : 0.105, start)
    gain.gain.exponentialRampToValueAtTime(SILENCE, start + duration)
    osc.connect(gain)
    gain.connect(out)
    osc.start(start)
    osc.stop(start + duration + 0.02)
  }

  private scheduleNoise(
    out: AudioNode,
    start: number,
    duration: number,
    peak: number,
    highpass: number,
  ): void {
    const ctx = this.ctx
    if (ctx === null) return
    if (this.noiseBuffer === null) {
      this.noiseBuffer = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate)
      const data = this.noiseBuffer.getChannelData(0)
      for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1
    }
    const source = ctx.createBufferSource()
    const filter = ctx.createBiquadFilter()
    const gain = ctx.createGain()
    source.buffer = this.noiseBuffer
    filter.type = 'highpass'
    filter.frequency.value = highpass
    gain.gain.setValueAtTime(peak, start)
    gain.gain.exponentialRampToValueAtTime(SILENCE, start + duration)
    source.connect(filter)
    filter.connect(gain)
    gain.connect(out)
    const maxOffset = Math.max(0, this.noiseBuffer.duration - duration)
    source.start(start, Math.random() * maxOffset, duration)
  }
}

export const bgm = new BgmEngine()

declare global {
  interface Window {
    __bgm?: BgmEngine
    __bgmHistory?: readonly (BgmTrackId | null)[]
  }
}

if (typeof window !== 'undefined') {
  window.__bgm = bgm
  window.__bgmHistory = bgm.trackHistory
}
