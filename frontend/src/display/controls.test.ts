import { describe, expect, it } from 'vitest'
import { focusedSelectionButtons, modeSelectionButtons } from './controls'

describe('display controls', () => {
  it('moves through the mode menu before confirming the clicked option', () => {
    expect(modeSelectionButtons('rules', 'game')).toEqual(['right', 'right', 'enter'])
    expect(modeSelectionButtons('lang', 'rules')).toEqual(['right', 'enter'])
    expect(modeSelectionButtons('practice', 'practice')).toEqual(['enter'])
  })

  it('selects an unfocused two-option action before confirming it', () => {
    const buttonForTarget = (target: 'back' | 'help') => (target === 'back' ? 'left' : 'right')
    expect(focusedSelectionButtons(null, 'help', buttonForTarget)).toEqual(['right', 'enter'])
    expect(focusedSelectionButtons('back', 'back', buttonForTarget)).toEqual(['enter'])
  })
})
