// 判定結果 → 演出表示の純関数(テスト対象)。scored の +N は言語非依存(§5.13)。

import type { Judge, Lang } from '../../contracts/ws'
import { t } from '../../i18n/strings'

export const JUDGE_FLASH_MS = 1600

export type JudgeFlashKind = 'scored' | 'failed' | 'duplicate'

export interface JudgeFlashView {
  kind: JudgeFlashKind
  text: string
}

export function judgeFlashView(judge: Judge, lang: Lang): JudgeFlashView {
  switch (judge.result) {
    case 'scored':
      return { kind: 'scored', text: `+${judge.points}` }
    case 'unclearable':
      return { kind: 'failed', text: t(lang, 'judgeFail') }
    default:
      return { kind: 'duplicate', text: t(lang, 'judgeDup') }
  }
}
