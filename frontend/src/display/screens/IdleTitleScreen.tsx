// 待機画面(タイトル)。仕様§5.2: ロゴ・タイトル・PRESS ENTER の点滅表示。
// タイトルロゴ画像は未確定(仕様§10)のためテキストロゴで実装する。

import type { Lang } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'

export function IdleTitleScreen({ lang }: { lang: Lang }) {
  return (
    <div className="retro-screen">
      <h1 className="retro-title">HANOI CUBE</h1>
      <div className="retro-text" style={{ fontSize: '2.2vw' }}>
        {t(lang, 'titleSubtitle')}
      </div>
      <div className="retro-text" style={{ fontSize: '2vw', marginTop: '6vh' }}>
        <Blink>▶ {t(lang, 'titlePressEnter')} ◀</Blink>
      </div>
    </div>
  )
}
