// デモ用のプレイ記録(/records/demo)。Firestore なしで記録画面の全表示を確認できる
// (開発・ブースでの動作確認用。本物の play_id とは衝突しない)。
// 盤面と結果は実際の判定ルール(precompute.json)と整合させてある:
//   LMS// = 21点(3箱×7手)、//LMS はその鏡像 → duplicate_mirror、
//   LMS/MS/L = クリア不可、L/MS/L = 60点(4箱×15手)、同サイズ入替の再判定 → duplicate_same

import type { PlayDoc } from './contracts/play'

export const demoPlay: PlayDoc = {
  player_name: 'デモたろう',
  score: 81,
  fail_count: 1,
  played_at: '2026-08-21T10:00:00+09:00',
  judgements: [
    {
      seq: 1,
      board: 'LMS//',
      elapsed_ms: 8_000,
      result: 'scored',
      points: 21,
      min_moves: 7,
      dup_of_seq: null,
      tower_box_ids: { a: ['large-1', 'medium-1', 'small-1'], b: [], c: [] },
    },
    {
      seq: 2,
      board: '//LMS',
      elapsed_ms: 16_500,
      result: 'duplicate_mirror',
      points: 0,
      min_moves: 7,
      dup_of_seq: 1,
      tower_box_ids: { a: [], b: [], c: ['large-1', 'medium-1', 'small-1'] },
    },
    {
      seq: 3,
      board: 'LMS/MS/L',
      elapsed_ms: 30_000,
      result: 'unclearable',
      points: 0,
      min_moves: null,
      dup_of_seq: null,
      tower_box_ids: {
        a: ['large-1', 'medium-1', 'small-1'],
        b: ['medium-2', 'small-2'],
        c: ['large-2'],
      },
    },
    {
      seq: 4,
      board: 'L/MS/L',
      elapsed_ms: 42_000,
      result: 'scored',
      points: 60,
      min_moves: 15,
      dup_of_seq: null,
      tower_box_ids: { a: ['large-1'], b: ['medium-1', 'small-1'], c: ['large-2'] },
    },
    {
      seq: 5,
      board: 'L/MS/L',
      elapsed_ms: 55_000,
      result: 'duplicate_same',
      points: 0,
      min_moves: 15,
      dup_of_seq: 4,
      tower_box_ids: { a: ['large-2'], b: ['medium-1', 'small-1'], c: ['large-1'] },
    },
  ],
}
