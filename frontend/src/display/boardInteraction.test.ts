import { describe, expect, it } from 'vitest'
import type { CvBoardUpdate } from '../contracts/cv'
import { isSelectableBox, towerForBox } from './boardInteraction'

const board: CvBoardUpdate = {
  kind: 'board',
  t_ms: 0,
  towers: ['LM', 'S', ''],
  board: 'LM/S/',
  legal: true,
  violations: [],
  staging_box_ids: ['large-2'],
  tower_box_ids: [['large-1', 'medium-1'], ['small-1'], []],
}

describe('3D board selection', () => {
  it('allows staged boxes and tower tops, but not buried boxes', () => {
    expect(isSelectableBox(board, 'large-2')).toBe(true)
    expect(isSelectableBox(board, 'medium-1')).toBe(true)
    expect(isSelectableBox(board, 'large-1')).toBe(false)
  })

  it('uses an occupied box as a click target for its tower', () => {
    expect(towerForBox(board, 'medium-1')).toBe('A')
    expect(towerForBox(board, 'small-1')).toBe('B')
    expect(towerForBox(board, 'large-2')).toBeNull()
  })
})
