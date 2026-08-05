import { afterEach, describe, expect, it, vi } from 'vitest'
import { BgmEngine } from './engine'

class FakeAudioParam {
  value = 0

  setValueAtTime(value: number): this {
    this.value = value
    return this
  }

  linearRampToValueAtTime(value: number): this {
    this.value = value
    return this
  }

  exponentialRampToValueAtTime(value: number): this {
    this.value = value
    return this
  }

  cancelAndHoldAtTime(): this {
    return this
  }
}

class FakeAudioNode {
  connect(): FakeAudioNode {
    return this
  }

  disconnect(): void {}
}

class FakeGain extends FakeAudioNode {
  gain = new FakeAudioParam()
}

class FakeOscillator extends FakeAudioNode {
  type: OscillatorType = 'sine'
  frequency = new FakeAudioParam()
  detune = new FakeAudioParam()

  start(): void {}
  stop(): void {}
}

class FakeFilter extends FakeAudioNode {
  type: BiquadFilterType = 'lowpass'
  frequency = new FakeAudioParam()
  Q = new FakeAudioParam()
}

class FakeCompressor extends FakeAudioNode {
  threshold = new FakeAudioParam()
  knee = new FakeAudioParam()
  ratio = new FakeAudioParam()
  attack = new FakeAudioParam()
  release = new FakeAudioParam()
}

class FakeAudioContext {
  state: AudioContextState = 'running'
  currentTime = 0
  sampleRate = 48_000
  destination = new FakeAudioNode()

  createGain(): FakeGain {
    return new FakeGain()
  }

  createDynamicsCompressor(): FakeCompressor {
    return new FakeCompressor()
  }

  createBiquadFilter(): FakeFilter {
    return new FakeFilter()
  }

  createOscillator(): FakeOscillator {
    return new FakeOscillator()
  }

  resume(): Promise<void> {
    return Promise.resolve()
  }
}

describe('BgmEngine', () => {
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('アンロック前でも希望曲を保持し、切替履歴を記録する', () => {
    const engine = new BgmEngine()
    engine.setTrack('waiting')
    engine.setTrack('gameplay')
    engine.setTrack('result')
    expect(engine.requestedTrack).toBe('result')
    expect(engine.trackHistory).toEqual(['waiting', 'gameplay', 'result'])
    expect(engine.playbackState).toEqual({
      context: 'locked',
      activeTrack: null,
      scheduledNotes: 0,
      startedTracks: [],
    })
  })

  it('同じ曲の再指定では頭出しせず、履歴も増やさない', () => {
    const engine = new BgmEngine()
    engine.setTrack('waiting')
    engine.setTrack('waiting')
    engine.setTrack(null)
    engine.setTrack(null)
    expect(engine.trackHistory).toEqual(['waiting', null])
  })

  it('アンロック後はAudioContextを起動し、希望曲のノートを実際にスケジュールする', () => {
    vi.useFakeTimers()
    vi.stubGlobal('AudioContext', FakeAudioContext)
    const engine = new BgmEngine()
    engine.setTrack('waiting')
    engine.unlock()

    expect(engine.playbackState.context).toBe('running')
    expect(engine.playbackState.activeTrack).toBe('waiting')
    expect(engine.playbackState.startedTracks).toEqual(['waiting'])
    expect(engine.playbackState.scheduledNotes).toBeGreaterThan(0)

    engine.setTrack(null)
  })
})
