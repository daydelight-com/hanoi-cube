export type BgmTrackId = 'waiting' | 'gameplay' | 'result'

export type BgmVoice = 'lead' | 'arp' | 'bass' | 'pad'

export interface BgmNote {
  step: number
  midi: number
  length: number
  voice: BgmVoice
  velocity?: number
}

export interface BgmTrack {
  id: BgmTrackId
  title: string
  bpm: number
  bars: number
  gain: number
  notes: readonly BgmNote[]
  drums: {
    kick: readonly number[]
    snare: readonly number[]
    hat: readonly number[]
  }
}

const STEPS_PER_BAR = 16

type PatternCell = readonly [offset: number, midi: number, length: number]

interface Harmony {
  bass: number
  pad: readonly number[]
  arp: readonly number[]
}

function addNote(
  notes: BgmNote[],
  bar: number,
  offset: number,
  midi: number,
  length: number,
  voice: BgmVoice,
  velocity: number,
): void {
  notes.push({ step: bar * STEPS_PER_BAR + offset, midi, length, voice, velocity })
}

function addPattern(
  notes: BgmNote[],
  bar: number,
  voice: BgmVoice,
  pattern: readonly PatternCell[],
  velocity: number,
): void {
  for (const [offset, midi, length] of pattern) {
    addNote(notes, bar, offset, midi, length, voice, velocity)
  }
}

function addPad(notes: BgmNote[], bar: number, chord: readonly number[], velocity: number): void {
  for (const midi of chord) addNote(notes, bar, 0, midi, STEPS_PER_BAR, 'pad', velocity)
}

function addDrumBar(target: number[], bar: number, offsets: readonly number[]): void {
  for (const offset of offsets) target.push(bar * STEPS_PER_BAR + offset)
}

function ordered(notes: BgmNote[]): BgmNote[] {
  const voiceOrder: Record<BgmVoice, number> = { pad: 0, bass: 1, arp: 2, lead: 3 }
  return notes.sort(
    (left, right) =>
      left.step - right.step ||
      voiceOrder[left.voice] - voiceOrder[right.voice] ||
      left.midi - right.midi,
  )
}

const WAITING_HARMONY: readonly Harmony[] = [
  { bass: 45, pad: [57, 60, 64], arp: [69, 72, 76, 81] }, // Am(add9)
  { bass: 41, pad: [53, 57, 60, 64], arp: [65, 69, 72, 76] }, // Fmaj7
  { bass: 48, pad: [55, 60, 64, 71], arp: [67, 72, 76, 83] }, // Cmaj7/G
  { bass: 43, pad: [55, 59, 62, 64], arp: [67, 71, 74, 76] }, // G6
  { bass: 45, pad: [57, 60, 64, 67], arp: [69, 72, 76, 79] }, // Am7
  { bass: 38, pad: [50, 53, 57, 60], arp: [62, 65, 69, 72] }, // Dm7
  { bass: 41, pad: [53, 57, 60, 64], arp: [65, 69, 72, 76] }, // Fmaj7
  { bass: 40, pad: [52, 55, 59, 62], arp: [64, 67, 71, 74] }, // Em7
]

// The melody deliberately leaves whole bars open so UI and judging effects remain prominent.
const WAITING_LEAD: readonly (readonly PatternCell[])[] = [
  [
    [4, 72, 2],
    [7, 76, 1],
    [10, 79, 2],
    [14, 76, 2],
  ],
  [
    [2, 72, 2],
    [6, 69, 2],
    [10, 67, 2],
    [14, 69, 2],
  ],
  [],
  [
    [6, 71, 2],
    [10, 74, 2],
    [14, 79, 2],
  ],
  [
    [4, 76, 2],
    [8, 79, 2],
    [12, 81, 3],
  ],
  [
    [2, 77, 2],
    [6, 76, 2],
    [10, 72, 3],
  ],
  [],
  [
    [4, 71, 2],
    [8, 74, 2],
    [12, 76, 2],
    [14, 71, 2],
  ],
  [
    [2, 69, 2],
    [6, 72, 2],
    [10, 76, 2],
    [14, 79, 2],
  ],
  [
    [4, 77, 2],
    [8, 76, 2],
    [12, 72, 3],
  ],
  [
    [2, 76, 2],
    [6, 79, 2],
    [10, 84, 3],
  ],
  [],
  [
    [4, 81, 2],
    [7, 79, 1],
    [10, 76, 2],
    [14, 72, 2],
  ],
  [
    [2, 69, 2],
    [6, 72, 2],
    [10, 77, 3],
  ],
  [],
  [
    [4, 74, 2],
    [8, 71, 2],
    [12, 69, 4],
  ],
]

function makeWaitingTrack(): BgmTrack {
  const notes: BgmNote[] = []
  const kick: number[] = []
  const snare: number[] = []
  const hat: number[] = []

  for (let bar = 0; bar < 16; bar += 1) {
    const harmony = WAITING_HARMONY[bar % WAITING_HARMONY.length]
    addPad(notes, bar, harmony.pad, 0.18)

    addNote(notes, bar, 0, harmony.bass, 4, 'bass', 0.35)
    addNote(notes, bar, 8, harmony.bass + 7, 3, 'bass', 0.28)
    if (bar % 2 === 1) addNote(notes, bar, 12, harmony.bass + 12, 2, 'bass', 0.24)

    const arpOrder = bar % 2 === 0 ? [0, 1, 2, 1] : [2, 1, 0, 1]
    const arpOffsets = [2, 6, 10, 14]
    for (let index = 0; index < arpOffsets.length; index += 1) {
      addNote(notes, bar, arpOffsets[index], harmony.arp[arpOrder[index]], 2, 'arp', 0.25)
    }

    addPattern(notes, bar, 'lead', WAITING_LEAD[bar], 0.36)

    addDrumBar(kick, bar, bar % 4 === 3 ? [0] : bar % 2 === 0 ? [0, 8] : [0, 10])
    addDrumBar(snare, bar, [4, 12])
    addDrumBar(hat, bar, bar % 8 === 7 ? [2, 6, 10, 14, 15] : [2, 6, 10, 14])
  }

  return {
    id: 'waiting',
    title: 'NEON STACKS',
    bpm: 120,
    bars: 16,
    gain: 0.34,
    notes: ordered(notes),
    drums: { kick, snare, hat },
  }
}

const GAMEPLAY_HARMONY: readonly Harmony[] = [
  { bass: 45, pad: [57, 60, 64], arp: [69, 72, 76, 81] }, // Am
  { bass: 41, pad: [53, 57, 60], arp: [65, 69, 72, 77] }, // F
  { bass: 36, pad: [55, 60, 64], arp: [67, 72, 76, 79] }, // C/G
  { bass: 43, pad: [55, 59, 62], arp: [67, 71, 74, 79] }, // G
]

const GAMEPLAY_MELODY: readonly (readonly number[])[] = [
  [76, 79, 81, 84, 81, 79],
  [77, 76, 72, 69, 72, 76],
  [76, 79, 84, 83, 79, 76],
  [74, 79, 83, 81, 79, 74],
  [69, 72, 76, 81, 84, 81],
  [77, 81, 84, 81, 76, 72],
  [79, 84, 88, 84, 83, 79],
  [79, 83, 86, 83, 81, 71],
]

const GAMEPLAY_ARP_OFFSETS: readonly (readonly number[])[] = [
  [2, 6, 10, 14],
  [0, 2, 4, 6, 8, 10, 12, 14],
  [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14],
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
]

const GAMEPLAY_BASS: readonly (readonly (readonly [number, number, number])[])[] = [
  [
    [0, 0, 4],
    [8, 0, 3],
  ],
  [
    [0, 0, 3],
    [6, 12, 2],
    [8, 0, 3],
    [14, 7, 2],
  ],
  [
    [0, 0, 2],
    [4, 7, 2],
    [8, 12, 2],
    [12, 7, 2],
  ],
  [
    [0, 0, 2],
    [3, 7, 1],
    [6, 12, 2],
    [8, 0, 2],
    [11, 12, 1],
    [14, 7, 2],
  ],
]

const GAMEPLAY_LEAD_OFFSETS: readonly (readonly number[])[] = [
  [4, 10],
  [2, 7, 12],
  [2, 5, 8, 11, 14],
  [1, 4, 7, 10, 13, 14],
]

function makeGameplayTrack(): BgmTrack {
  const notes: BgmNote[] = []
  const kick: number[] = []
  const snare: number[] = []
  const hat: number[] = []
  const arpShape = [0, 1, 2, 1, 3, 2, 1, 2]

  for (let bar = 0; bar < 32; bar += 1) {
    const phase = Math.floor(bar / 8)
    const harmony = GAMEPLAY_HARMONY[bar % GAMEPLAY_HARMONY.length]
    addPad(notes, bar, harmony.pad, 0.13 + phase * 0.015)

    for (const [offset, interval, length] of GAMEPLAY_BASS[phase]) {
      addNote(notes, bar, offset, harmony.bass + interval, length, 'bass', 0.34 + phase * 0.03)
    }

    const arpOffsets = GAMEPLAY_ARP_OFFSETS[phase]
    for (let index = 0; index < arpOffsets.length; index += 1) {
      addNote(
        notes,
        bar,
        arpOffsets[index],
        harmony.arp[arpShape[index % arpShape.length]],
        phase === 0 ? 2 : 1,
        'arp',
        0.2 + phase * 0.025,
      )
    }

    // The opening eight bars state only half the lead phrase; each later phase fills in more notes.
    if (phase !== 0 || bar % 2 === 0) {
      const melody = GAMEPLAY_MELODY[bar % GAMEPLAY_MELODY.length]
      const offsets = GAMEPLAY_LEAD_OFFSETS[phase]
      for (let index = 0; index < offsets.length; index += 1) {
        addNote(
          notes,
          bar,
          offsets[index],
          melody[index],
          phase < 2 ? 2 : 1,
          'lead',
          0.33 + phase * 0.025,
        )
      }
    }

    const kickPattern = [
      [0, 8],
      [0, 6, 8],
      [0, 3, 8, 11],
      [0, 3, 6, 8, 11, 14],
    ][phase]
    const snarePattern = [
      [4, 12],
      [4, 12],
      [4, 10, 12],
      [4, 7, 12, 15],
    ][phase]
    addDrumBar(kick, bar, kickPattern)
    addDrumBar(snare, bar, snarePattern)
    addDrumBar(hat, bar, GAMEPLAY_ARP_OFFSETS[phase])
  }

  return {
    id: 'gameplay',
    title: 'CUBE RUSH',
    bpm: 128,
    bars: 32,
    gain: 0.28,
    notes: ordered(notes),
    drums: { kick, snare, hat },
  }
}

const RESULT_HARMONY: readonly Harmony[] = [
  { bass: 36, pad: [60, 64, 67, 71], arp: [72, 76, 79, 83] }, // Cmaj7
  { bass: 47, pad: [59, 62, 67, 71], arp: [71, 74, 79, 83] }, // G/B
  { bass: 45, pad: [57, 60, 64, 67], arp: [69, 72, 76, 79] }, // Am7
  { bass: 43, pad: [55, 59, 64, 67], arp: [67, 71, 76, 79] }, // Em7/G
  { bass: 41, pad: [53, 57, 60, 64], arp: [65, 69, 72, 76] }, // Fmaj7
  { bass: 40, pad: [52, 55, 60, 64], arp: [64, 67, 72, 76] }, // C/E
  { bass: 38, pad: [50, 53, 57, 60], arp: [62, 65, 69, 72] }, // Dm7
  { bass: 43, pad: [55, 59, 62, 65], arp: [67, 71, 74, 77] }, // G7
  { bass: 36, pad: [60, 64, 67, 74], arp: [72, 76, 79, 86] }, // Cmaj9
  { bass: 45, pad: [57, 60, 64, 67], arp: [69, 72, 76, 79] }, // Am7
  { bass: 41, pad: [53, 57, 60, 64], arp: [65, 69, 72, 76] }, // Fmaj7
  { bass: 43, pad: [55, 59, 62, 65], arp: [67, 71, 74, 77] }, // G7 -> loop to C
]

const RESULT_LEAD: readonly (readonly PatternCell[])[] = [
  [
    [0, 72, 3],
    [4, 76, 3],
    [8, 79, 3],
    [12, 84, 4],
  ],
  [
    [2, 83, 2],
    [6, 86, 2],
    [10, 83, 2],
    [14, 79, 2],
  ],
  [
    [0, 81, 3],
    [4, 84, 3],
    [8, 88, 3],
    [12, 84, 4],
  ],
  [
    [2, 79, 2],
    [6, 83, 2],
    [10, 88, 2],
    [14, 86, 2],
  ],
  [
    [0, 77, 3],
    [4, 81, 3],
    [8, 84, 3],
    [12, 81, 4],
  ],
  [
    [2, 76, 2],
    [6, 79, 2],
    [10, 84, 2],
    [14, 79, 2],
  ],
  [
    [0, 74, 3],
    [4, 77, 3],
    [8, 81, 3],
    [12, 84, 4],
  ],
  [
    [2, 83, 2],
    [6, 86, 2],
    [10, 89, 2],
    [14, 86, 2],
  ],
  [
    [0, 84, 2],
    [3, 88, 2],
    [6, 91, 2],
    [10, 88, 2],
    [14, 84, 2],
  ],
  [
    [0, 81, 2],
    [3, 84, 2],
    [6, 88, 2],
    [10, 84, 2],
    [14, 81, 2],
  ],
  [
    [0, 77, 2],
    [3, 81, 2],
    [6, 84, 2],
    [10, 81, 2],
    [14, 77, 2],
  ],
  [
    [0, 79, 2],
    [3, 83, 2],
    [6, 86, 2],
    [10, 83, 2],
    [14, 71, 2],
  ],
]

function makeResultTrack(): BgmTrack {
  const notes: BgmNote[] = []
  const kick: number[] = []
  const snare: number[] = []
  const hat: number[] = []
  const arpShape = [0, 1, 2, 3, 2, 1, 3, 1]

  for (let bar = 0; bar < 12; bar += 1) {
    const harmony = RESULT_HARMONY[bar]
    addPad(notes, bar, harmony.pad, 0.19)

    // 名前入力やUIクリックが続く曲なので、低音は全編を通して半音符中心に保つ。
    const bassPattern = [
      [0, 0, 5],
      [8, 12, 4],
    ]
    for (const [offset, interval, length] of bassPattern) {
      addNote(notes, bar, offset, harmony.bass + interval, length, 'bass', 0.34)
    }

    const arpOffsets = bar < 4 ? [2, 6, 10, 14] : bar < 8 ? [2, 5, 8, 11, 14] : [2, 6, 10, 14]
    for (let index = 0; index < arpOffsets.length; index += 1) {
      addNote(
        notes,
        bar,
        arpOffsets[index],
        harmony.arp[arpShape[index % arpShape.length]],
        1,
        'arp',
        0.24,
      )
    }

    addPattern(notes, bar, 'lead', RESULT_LEAD[bar], bar < 8 ? 0.38 : 0.42)

    addDrumBar(kick, bar, [0, 8])
    addDrumBar(snare, bar, [4, 12])
    addDrumBar(hat, bar, [2, 6, 10, 14])
  }

  return {
    id: 'result',
    title: 'SCORE GLOW',
    bpm: 96,
    bars: 12,
    gain: 0.32,
    notes: ordered(notes),
    drums: { kick, snare, hat },
  }
}

export const BGM_TRACKS: Record<BgmTrackId, BgmTrack> = {
  waiting: makeWaitingTrack(),
  gameplay: makeGameplayTrack(),
  result: makeResultTrack(),
}

export function trackDurationSeconds(track: BgmTrack): number {
  return (track.bars * 4 * 60) / track.bpm
}
