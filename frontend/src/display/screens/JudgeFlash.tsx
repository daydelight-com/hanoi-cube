// 判定演出(仕様§5.6: 成功=+N と成功演出 / 失敗=失敗演出 / 判定済み=「判定済み」)。
// 練習・本番で共用。lastJudge の seq で新旧を区別し、一定時間で消える。

import { useEffect, useState } from 'react'
import type { Judge, Lang } from '../../contracts/ws'
import { JUDGE_FLASH_MS, judgeFlashView } from './judgeView'

export function JudgeFlash({ lang, judge }: { lang: Lang; judge: Judge | null }) {
  // 表示終了済みの seq を覚える(表示自体は judge の変化で宣言的に始まる)
  const [expiredSeq, setExpiredSeq] = useState<number | null>(null)

  useEffect(() => {
    if (judge === null) return
    const timer = setTimeout(() => setExpiredSeq(judge.seq), JUDGE_FLASH_MS)
    return () => clearTimeout(timer)
  }, [judge])

  if (judge === null || judge.seq === expiredSeq) return null
  const view = judgeFlashView(judge, lang)
  return (
    // key=seq で連続判定でもアニメーションを最初から再生する
    <div key={judge.seq} className={`retro-judge retro-judge--${view.kind}`}>
      {view.text}
    </div>
  )
}
