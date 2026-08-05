import { describe, expect, it } from 'vitest'
import { BGM_TRACKS, trackDurationSeconds } from './tracks'

const EXPECTED = {
  waiting: { title: 'NEON STACKS', bpm: 120, bars: 16, seconds: 32 },
  gameplay: { title: 'CUBE RUSH', bpm: 128, bars: 32, seconds: 60 },
  result: { title: 'SCORE GLOW', bpm: 96, bars: 12, seconds: 30 },
} as const

describe('BGM_TRACKS', () => {
  it('contains the three screen tracks with their intended loop durations', () => {
    expect(Object.keys(BGM_TRACKS).sort()).toEqual(['gameplay', 'result', 'waiting'])

    for (const id of Object.keys(EXPECTED) as (keyof typeof EXPECTED)[]) {
      const track = BGM_TRACKS[id]
      expect(track.id).toBe(id)
      expect(track.title).toBe(EXPECTED[id].title)
      expect(track.bpm).toBe(EXPECTED[id].bpm)
      expect(track.bars).toBe(EXPECTED[id].bars)
      expect(trackDurationSeconds(track)).toBe(EXPECTED[id].seconds)
    }
  })

  it('keeps every note and drum hit inside its loop', () => {
    for (const track of Object.values(BGM_TRACKS)) {
      const totalSteps = track.bars * 16
      expect(track.gain).toBeGreaterThan(0)
      expect(track.gain).toBeLessThanOrEqual(1)
      expect(track.notes.length).toBeGreaterThan(0)

      for (const note of track.notes) {
        expect(Number.isInteger(note.step)).toBe(true)
        expect(note.step).toBeGreaterThanOrEqual(0)
        expect(note.step).toBeLessThan(totalSteps)
        expect(Number.isInteger(note.midi)).toBe(true)
        expect(note.midi).toBeGreaterThanOrEqual(0)
        expect(note.midi).toBeLessThanOrEqual(127)
        expect(Number.isInteger(note.length)).toBe(true)
        expect(note.length).toBeGreaterThan(0)
        expect(note.step + note.length).toBeLessThanOrEqual(totalSteps)
        if (note.velocity !== undefined) {
          expect(note.velocity).toBeGreaterThan(0)
          expect(note.velocity).toBeLessThanOrEqual(1)
        }
      }

      for (const drum of Object.values(track.drums)) {
        expect(drum.length).toBeGreaterThan(0)
        for (const step of drum) {
          expect(Number.isInteger(step)).toBe(true)
          expect(step).toBeGreaterThanOrEqual(0)
          expect(step).toBeLessThan(totalSteps)
        }
      }
    }
  })

  it('gives every composition a distinct, nonempty arrangement using all four voices', () => {
    const signatures = Object.values(BGM_TRACKS).map((track) =>
      track.notes
        .map(({ step, midi, length, voice }) => `${step}:${midi}:${length}:${voice}`)
        .join('|'),
    )
    expect(new Set(signatures).size).toBe(3)

    for (const track of Object.values(BGM_TRACKS)) {
      expect(new Set(track.notes.map((note) => note.voice))).toEqual(
        new Set(['lead', 'arp', 'bass', 'pad']),
      )
    }
  })

  it('builds intensity across each eight-bar section of CUBE RUSH', () => {
    const track = BGM_TRACKS.gameplay
    const eventsPerSection = [0, 1, 2, 3].map((section) => {
      const firstStep = section * 8 * 16
      const lastStep = firstStep + 8 * 16
      const notes = track.notes.filter(
        (note) => note.step >= firstStep && note.step < lastStep,
      ).length
      const drums = Object.values(track.drums).reduce(
        (count, hits) => count + hits.filter((step) => step >= firstStep && step < lastStep).length,
        0,
      )
      return notes + drums
    })

    expect(eventsPerSection[1]).toBeGreaterThan(eventsPerSection[0])
    expect(eventsPerSection[2]).toBeGreaterThan(eventsPerSection[1])
    expect(eventsPerSection[3]).toBeGreaterThan(eventsPerSection[2])
  })

  it('keeps the final SCORE GLOW section sparse for name entry and UI sounds', () => {
    const track = BGM_TRACKS.result
    const eventsInBars = (firstBar: number, bars: number) => {
      const firstStep = firstBar * 16
      const lastStep = (firstBar + bars) * 16
      const notes = track.notes.filter(
        (note) => note.step >= firstStep && note.step < lastStep,
      ).length
      const drums = Object.values(track.drums).reduce(
        (count, hits) => count + hits.filter((step) => step >= firstStep && step < lastStep).length,
        0,
      )
      return notes + drums
    }

    expect(eventsInBars(8, 4)).toBeLessThanOrEqual(eventsInBars(4, 4))
  })
})
