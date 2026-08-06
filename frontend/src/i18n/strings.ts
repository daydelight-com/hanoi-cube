// 表示文言の日英辞書(仕様§5.13)。言語状態はサーバー配信の lang に従う
// (クライアント個別設定は持たない)。キーは Messages 型で両言語の網羅を強制する。
// ゲームタイトル・カウントダウン・スコア数値・プレイヤー名は言語非依存(§5.13)。

import type { Lang } from '../contracts/ws'

export interface Messages {
  // 待機(タイトル)
  titleSubtitle: string
  titlePressEnter: string
  // 待機(ランキング)/ ランキング共通
  rankingHeading: string
  rankingRank: string
  rankingName: string
  rankingScore: string
  rankingFails: string
  rankingEmpty: string
  // モード選択
  modeHeading: string
  modeRules: string
  modePractice: string
  modeGame: string
  modeHint: string
  // ルールダイアログ
  ruleClose: string
  rulePageNav: string
  // 練習
  practiceHeading: string
  practiceBack: string
  practiceHint: string
  // ゲーム(本番)共通ラベル
  scoreLabel: string
  timeLabel: string
  failLabel: string
  // 判定演出(scored は +N 表示のため言語非依存)
  judgeFail: string
  judgeDup: string
  // リザルト
  resultHeading: string
  resultRank: string
  resultNameLabel: string
  resultInputButton: string
  resultDecideButton: string
  resultTyping: string
  resultHint: string
  // ランキング
  rankingNext: string
  // QR
  qrHeading: string
  qrCaption: string
  qrNext: string
  // iPadコントローラ
  padNamePlaceholder: string
  padNameDone: string
  // 共通
  connecting: string
  disconnected: string
}

export const MESSAGES: Record<Lang, Messages> = {
  ja: {
    titleSubtitle: 'はこを ならべて スコアアタック!',
    titlePressEnter: 'けっていボタンで スタート',
    rankingHeading: 'ランキング',
    rankingRank: 'じゅんい',
    rankingName: 'なまえ',
    rankingScore: 'スコア',
    rankingFails: 'しっぱい',
    rankingEmpty: 'まだ きろくが ありません',
    modeHeading: 'モードをえらんでね',
    modeRules: 'ルールせつめい',
    modePractice: 'れんしゅう',
    modeGame: 'ほんばん',
    modeHint: '←→ でえらんで けっていボタン',
    ruleClose: 'けっていボタンで とじる',
    rulePageNav: '←→ でページきりかえ',
    practiceHeading: 'れんしゅう',
    practiceBack: 'もどる',
    practiceHint: 'はこを ならべて けっていで はんてい',
    scoreLabel: 'スコア',
    timeLabel: 'のこり',
    failLabel: 'しっぱい',
    judgeFail: 'しっぱい...',
    judgeDup: 'はんていずみ',
    resultHeading: 'けっか はっぴょう',
    resultRank: 'じゅんい',
    resultNameLabel: 'なまえ',
    resultInputButton: 'にゅうりょく',
    resultDecideButton: 'けってい',
    resultTyping: 'iPadで なまえを いれてね',
    resultHint: '←→ でえらんで けっていボタン',
    rankingNext: 'けっていボタンで つぎへ',
    qrHeading: 'きょうの きろく',
    qrCaption: 'スマホで よみとると きょうの プレイきろくが みられるよ',
    qrNext: 'けっていボタンで タイトルへ',
    padNamePlaceholder: 'なまえ(10もじまで)',
    padNameDone: 'かんりょう',
    connecting: 'サーバーに せつぞくちゅう...',
    disconnected: 'せつぞくが きれました さいせつぞくちゅう...',
  },
  en: {
    titleSubtitle: 'STACK THE BOXES, BEAT THE SCORE!',
    titlePressEnter: 'PRESS ENTER TO START',
    rankingHeading: 'RANKING',
    rankingRank: 'RANK',
    rankingName: 'NAME',
    rankingScore: 'SCORE',
    rankingFails: 'FAILS',
    rankingEmpty: 'NO RECORDS YET',
    modeHeading: 'SELECT MODE',
    modeRules: 'HOW TO PLAY',
    modePractice: 'PRACTICE',
    modeGame: 'GAME',
    modeHint: 'MOVE WITH ARROWS, PRESS ENTER',
    ruleClose: 'PRESS ENTER TO CLOSE',
    rulePageNav: 'TURN PAGES WITH ARROWS',
    practiceHeading: 'PRACTICE',
    practiceBack: 'BACK',
    practiceHint: 'ARRANGE BOXES AND PRESS ENTER TO JUDGE',
    scoreLabel: 'SCORE',
    timeLabel: 'TIME',
    failLabel: 'FAILS',
    judgeFail: 'FAILED...',
    judgeDup: 'ALREADY JUDGED',
    resultHeading: 'RESULT',
    resultRank: 'RANK',
    resultNameLabel: 'NAME',
    resultInputButton: 'INPUT',
    resultDecideButton: 'OK',
    resultTyping: 'TYPE YOUR NAME ON THE IPAD',
    resultHint: 'MOVE WITH ARROWS, PRESS ENTER',
    rankingNext: 'PRESS ENTER TO CONTINUE',
    qrHeading: "TODAY'S RECORD",
    qrCaption: 'SCAN WITH YOUR PHONE TO SEE YOUR PLAY RECORD',
    qrNext: 'PRESS ENTER FOR TITLE',
    padNamePlaceholder: 'NAME (MAX 10)',
    padNameDone: 'DONE',
    connecting: 'CONNECTING TO SERVER...',
    disconnected: 'CONNECTION LOST - RECONNECTING...',
  },
}

export function t(lang: Lang, key: keyof Messages): string {
  return MESSAGES[lang][key]
}

// ルールダイアログの5ページ(screens.md: page_count=5)。文言の正は
// docs/game/hanoi_arrange_rules.md。図版差し替え(§5.13)は後日。
export interface RulePage {
  title: string
  lines: string[]
}

export const RULE_PAGES: Record<Lang, RulePage[]> = {
  ja: [
    {
      title: 'ゲームのあらまし',
      lines: [
        'はこを とうに ならべて「はんてい」!',
        'クリアかのうな ならべかたなら とくてん。',
        'せいげんじかん 1ぷんで ハイスコアを めざそう。',
      ],
    },
    {
      title: 'ならべかたのルール',
      lines: [
        'うえに いくほど ちいさく つむこと。',
        'おなじ おおきさは おなじ とうに 1こまで。',
        '1つの とうには さいだい 3こまで。',
      ],
    },
    {
      title: 'はこの うごかしかた',
      lines: [
        '1かいに うごかせるのは いちばんうえの 1こだけ。',
        'いどうさきは からの とうか、',
        'じぶんより おおきい はこの うえだけ。',
      ],
    },
    {
      title: '「クリアかのう」とは',
      lines: [
        'ひだりから (a, b, c) この はこが',
        'ぎゃくの (c, b, a) に なるように',
        'はこを うごかせたら クリア!',
      ],
    },
    {
      title: 'とくてんと コツ',
      lines: [
        'とくてん = はこのかず × さいたんてすう。',
        'おなじ(かがみうつしも おなじ)ならべかたは 1かいだけ。',
        'むずかしい ならべかたほど こうとくてん!',
      ],
    },
  ],
  en: [
    {
      title: 'OVERVIEW',
      lines: [
        'Stack boxes on the towers and press JUDGE!',
        'A clearable layout earns points.',
        'Aim for a high score in 1 minute.',
      ],
    },
    {
      title: 'STACKING RULES',
      lines: [
        'Smaller boxes must go on top.',
        'Only one of each size per tower.',
        'Max 3 boxes per tower.',
      ],
    },
    {
      title: 'MOVING RULES',
      lines: [
        'Move only the top box, one at a time.',
        'Place it on an empty tower,',
        'or on a bigger box only.',
      ],
    },
    {
      title: 'WHAT IS "CLEARABLE"?',
      lines: [
        'With counts (a, b, c) from the left,',
        'move the boxes to reach (c, b, a)',
        'and you clear it!',
      ],
    },
    {
      title: 'SCORING & TIPS',
      lines: [
        'Points = number of boxes × minimum moves.',
        'Each layout (mirrors too) scores only once.',
        'Trickier layouts score higher!',
      ],
    },
  ],
}
