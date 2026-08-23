// 画面ルーター: サーバー配信の screen(screens.md の画面ID)に応じて描画する。
// S4: idle_title / idle_ranking / mode_select / rule_dialog、
// S5: practice / game_countdown / game_play / result / ranking / qr(全10画面)。

import type { ButtonName, Judge, Lang, ScreenState } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'
import { GameCountdownScreen, GamePlayScreen } from './GameScreens'
import { IdleRankingScreen } from './IdleRankingScreen'
import { IdleTitleScreen } from './IdleTitleScreen'
import { ModeSelectScreen } from './ModeSelectScreen'
import { PracticeScreen } from './PracticeScreen'
import { QrScreen } from './QrScreen'
import { RankingScreen } from './RankingScreen'
import { ResultScreen } from './ResultScreen'
import { RuleDialogScreen } from './RuleDialogScreen'

export function ScreenView({
  lang,
  screen,
  lastJudge,
  onButton,
  onModeSelect,
  onPracticeSelect,
  onResultSelect,
}: {
  lang: Lang
  screen: ScreenState | null
  lastJudge: Judge | null
  onButton: (button: ButtonName) => void
  onModeSelect: (target: 'rules' | 'practice' | 'game' | 'lang') => void
  onPracticeSelect: (target: 'back' | 'help') => void
  onResultSelect: (target: 'input' | 'decide') => void
}) {
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
      return <IdleTitleScreen lang={lang} onButton={onButton} />
    case 'idle_ranking':
      return <IdleRankingScreen lang={lang} entries={screen.ctx.entries} />
    case 'mode_select':
      return <ModeSelectScreen lang={lang} ctx={screen.ctx} onSelect={onModeSelect} />
    case 'rule_dialog':
      return <RuleDialogScreen lang={lang} ctx={screen.ctx} />
    case 'practice':
      return (
        <PracticeScreen
          lang={lang}
          ctx={screen.ctx}
          lastJudge={lastJudge}
          onSelect={onPracticeSelect}
        />
      )
    case 'game_countdown':
      return <GameCountdownScreen ctx={screen.ctx} />
    case 'game_play':
      return <GamePlayScreen lang={lang} ctx={screen.ctx} lastJudge={lastJudge} />
    case 'result':
      return <ResultScreen lang={lang} ctx={screen.ctx} onSelect={onResultSelect} />
    case 'ranking':
      return <RankingScreen lang={lang} ctx={screen.ctx} />
    case 'qr':
      return <QrScreen lang={lang} ctx={screen.ctx} />
  }
}
