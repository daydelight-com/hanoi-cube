// QR画面(仕様§5.9)。記録画面URL(事前採番の play_id)のQRを大きく表示する。
// アップロード未完了でもQRは表示する(記録画面側が「準備中」を出す)。

import { useEffect, useState } from 'react'
import { toDataURL } from 'qrcode'
import type { Lang, ScreenCtxMap } from '../../contracts/ws'
import { t } from '../../i18n/strings'
import { Blink, RetroFrame } from '../ui/Retro'

export function QrScreen({ lang, ctx }: { lang: Lang; ctx: ScreenCtxMap['qr'] }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    toDataURL(ctx.url, {
      errorCorrectionLevel: 'M',
      margin: 2,
      scale: 12,
      color: { dark: '#0a1a0a', light: '#e8ffe0' },
    })
      .then((url) => {
        if (!cancelled) setDataUrl(url)
      })
      .catch(() => {
        // 生成失敗時はURL文字列の表示のみ(下部に常時表示)にフォールバック
        if (!cancelled) setDataUrl(null)
      })
    return () => {
      cancelled = true
    }
  }, [ctx.url])

  return (
    <div className="retro-screen">
      <h2 className="retro-heading">{t(lang, 'qrHeading')}</h2>
      <RetroFrame style={{ padding: '2vh 2vh' }}>
        {dataUrl ? (
          <img className="retro-qr" src={dataUrl} alt={ctx.url} />
        ) : (
          <div className="retro-qr retro-qr--placeholder" />
        )}
      </RetroFrame>
      <div className="retro-text">{t(lang, 'qrCaption')}</div>
      <div className="retro-qr-url">{ctx.url}</div>
      <div className="retro-text">
        <Blink>{t(lang, 'qrNext')}</Blink>
      </div>
    </div>
  )
}
