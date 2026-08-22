// シェア機能(記録ページのシェアボタン用)。
// Web Share API が使える端末(スマホ想定)ではOSのシェアシートを開き、
// 使えない環境では X(Twitter) のツイート画面へフォールバックする。

import type { PlayDoc } from './contracts/play'

/** シェア本文。スコアを載せて「自分の記録」を共有したくなる文にする */
export function shareText(play: Pick<PlayDoc, 'score'>): string {
  return `「Cubeでハノイ」で ${play.score}てん とったよ! #pyconjp`
}

/** Web Share API 非対応環境向けの X 投稿画面URL */
export function xIntentUrl(text: string, url: string): string {
  const params = new URLSearchParams({ text, url })
  return `https://twitter.com/intent/tweet?${params.toString()}`
}

/**
 * シェア実行。キャンセル(AbortError)は正常系として握りつぶし、
 * それ以外の失敗(権限拒否等)は X フォールバックに切り替えてボタン無反応を避ける。
 */
export async function sharePlay(play: Pick<PlayDoc, 'score'>, url: string): Promise<void> {
  const text = shareText(play)
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({ text, url })
      return
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return
    }
  }
  window.open(xIntentUrl(text, url), '_blank', 'noopener')
}
