// plays/{play_id} の1件読み取り(仕様§8.2、契約: firestore.md §1)。
// Firestore Web クライアントSDK(lite)で直接読む。書き込みはルールで全面禁止されている。

import { initializeApp, type FirebaseApp } from 'firebase/app'
import {
  connectFirestoreEmulator,
  doc,
  getDoc,
  getFirestore,
  type Firestore,
} from 'firebase/firestore/lite'
import { isPlayDoc, type PlayDoc } from './contracts/play'
import { demoPlay } from './demo'

export type FetchResult =
  | { status: 'ok'; play: PlayDoc }
  | { status: 'not_found' } // ドキュメント不存在 = アップロード前(準備中)
  | { status: 'unconfigured' } // Firebase 設定なしのビルド(デプロイ設定漏れ)

let db: Firestore | null | undefined

function firestoreDb(): Firestore | null {
  if (db !== undefined) return db
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined
  if (!projectId) {
    db = null
    return db
  }
  const app: FirebaseApp = initializeApp({
    projectId,
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  })
  db = getFirestore(app)
  // エミュレータ接続(ローカル通し検証用。本番ビルドでは未設定)
  const emulator = import.meta.env.VITE_FIRESTORE_EMULATOR_HOST as string | undefined
  if (emulator) {
    const [host, port] = emulator.split(':')
    connectFirestoreEmulator(db, host, Number(port))
  }
  return db
}

/** 通信失敗は例外のまま伝える(呼び出し側が再試行UIを出す) */
export async function fetchPlay(playId: string): Promise<FetchResult> {
  if (playId === 'demo') return { status: 'ok', play: demoPlay }
  const store = firestoreDb()
  if (store === null) return { status: 'unconfigured' }
  const snapshot = await getDoc(doc(store, 'plays', playId))
  const data = snapshot.data()
  if (data === undefined) return { status: 'not_found' }
  if (!isPlayDoc(data)) throw new Error('unexpected document shape')
  return { status: 'ok', play: data }
}
