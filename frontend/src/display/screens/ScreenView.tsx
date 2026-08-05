// 画面ルーター: サーバー配信の screen(screens.md の画面ID)に応じて描画する。
// S4 実装対象: idle_title / idle_ranking / mode_select / rule_dialog。
// practice / game_* / result / ranking / qr は S5 で本実装(暫定プレースホルダ)。

import type { Lang, ScreenState } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'
import { IdleRankingScreen } from './IdleRankingScreen'
import { IdleTitleScreen } from './IdleTitleScreen'
import { ModeSelectScreen } from './ModeSelectScreen'
import { RuleDialogScreen } from './RuleDialogScreen'

function ScreenPlaceholder({ lang, screenId }: { lang: Lang; screenId: string }) {
  // 3D盤面が見えるよう背景は暗くしない(practice/game 系はS5で本実装)
  return (
    <div className="retro-screen retro-screen--clear" style={{ justifyContent: 'flex-start' }}>
      <div className="retro-text" style={{ marginTop: '4vh' }}>
        [{screenId}] {t(lang, 'placeholderNote')}
      </div>
    </div>
  )
}

export function ScreenView({ lang, screen }: { lang: Lang; screen: ScreenState | null }) {
  if (screen === null) {
    return (
      <div className="retro-screen">
        <div className="retro-text" style={{ fontSize: '2vw' }}>
          <Blink>{t(lang, 'connecting')}</Blink>
        </div>
      </div>
    )
  }
  switch (screen.screen) {
    case 'idle_title':
      return <IdleTitleScreen lang={lang} />
    case 'idle_ranking':
      return <IdleRankingScreen lang={lang} entries={screen.ctx.entries} />
    case 'mode_select':
      return <ModeSelectScreen lang={lang} ctx={screen.ctx} />
    case 'rule_dialog':
      return <RuleDialogScreen lang={lang} ctx={screen.ctx} />
    default:
      return <ScreenPlaceholder lang={lang} screenId={screen.screen} />
  }
}
