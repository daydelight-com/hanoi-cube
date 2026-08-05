// 練習画面(仕様§5.5)。制限時間なし・記録に残らない。背景は透過で3D盤面を見せる。
// 上部左「戻る」・右「?」。選択状態(ctx.selection)はサーバーに追従する。

import type { Judge, Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { MenuItem } from '../ui/Retro'
import { JudgeFlash } from './JudgeFlash'

export function PracticeScreen({
  lang,
  ctx,
  lastJudge,
}: {
  lang: Lang
  ctx: ScreenCtxMap['practice']
  lastJudge: Judge | null
}) {
  return (
    <div className="retro-screen retro-screen--clear">
      <div className="retro-hud retro-hud--left">
        <MenuItem focused={ctx.selection === 'back'}>{t(lang, 'practiceBack')}</MenuItem>
      </div>
      <div className="retro-hud retro-hud--right">
        <MenuItem focused={ctx.selection === 'help'}>?</MenuItem>
      </div>
      <div className="retro-hud retro-hud--center">
        <div className="retro-hud-label">{t(lang, 'practiceHeading')}</div>
        <div className="retro-hud-value">
          {t(lang, 'scoreLabel')} {ctx.score}
        </div>
      </div>
      <JudgeFlash lang={lang} judge={lastJudge} />
      <div className="retro-text retro-bottom-hint">{t(lang, 'practiceHint')}</div>
    </div>
  )
}
