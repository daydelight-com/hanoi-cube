// モード選択画面。仕様§5.3: 「ルール説明」「練習」「本番」横並び+右上に言語切替。
// フォーカスはサーバーの ctx.focus に追従する(表示専用)。

import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { MenuItem } from '../ui/Retro'

export function ModeSelectScreen({ lang, ctx }: { lang: Lang; ctx: ScreenCtxMap['mode_select'] }) {
  return (
    <div className="retro-screen">
      <div style={{ position: 'absolute', top: '4vh', right: '3vw' }}>
        <MenuItem focused={ctx.focus === 'lang'}>JA / EN</MenuItem>
      </div>
      <h2 className="retro-heading" style={{ marginBottom: '6vh' }}>
        {t(lang, 'modeHeading')}
      </h2>
      <div style={{ display: 'flex', gap: '3vw' }}>
        <MenuItem focused={ctx.focus === 'rules'}>{t(lang, 'modeRules')}</MenuItem>
        <MenuItem focused={ctx.focus === 'practice'}>{t(lang, 'modePractice')}</MenuItem>
        <MenuItem focused={ctx.focus === 'game'}>{t(lang, 'modeGame')}</MenuItem>
      </div>
      <div className="retro-text" style={{ marginTop: '8vh' }}>
        {t(lang, 'modeHint')}
      </div>
    </div>
  )
}
