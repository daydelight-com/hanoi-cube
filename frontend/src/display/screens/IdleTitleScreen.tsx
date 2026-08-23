// 待機画面(タイトル)。仕様§5.2: ロゴ・タイトル・PRESS ENTER の点滅表示。
// タイトルロゴ画像は未確定(仕様§10)のためテキストロゴで実装する。

import type { ButtonName, Lang } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink } from '../ui/Retro'

export function IdleTitleScreen({
  lang,
  onButton,
}: {
  lang: Lang
  onButton: (button: ButtonName) => void
}) {
  return (
    <div className="retro-screen">
      <h1 className="retro-title">Cubeでハノイ</h1>
      <div className="retro-text" style={{ fontSize: '2.2vw' }}>
        {t(lang, 'titleSubtitle')}
      </div>
      <button
        type="button"
        className="retro-text retro-text-button"
        style={{ fontSize: '2vw', marginTop: '6vh' }}
        onClick={() => onButton('enter')}
      >
        <Blink>▶ {t(lang, 'titlePressEnter')} ◀</Blink>
      </button>
    </div>
  )
}
