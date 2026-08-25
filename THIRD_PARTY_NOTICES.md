# 第三者の著作物について (Third-Party Notices)

Hanoi Cube には以下の第三者の著作物が同梱されています。それぞれ原著作者のライセンスが
適用され、本リポジトリの LICENSE(Apache-2.0)の適用範囲外です。

(PyPI / npm から取得する依存パッケージそのものはリポジトリに同梱していないため、ここには
記載していません。依存の一覧は `server/pyproject.toml`、`pyxel_app/pyproject.toml`、
`frontend/package.json`、`cloud/record/package.json` にありますが、これらにライセンス種別は
書かれていません。各パッケージのライセンスは配布元(PyPI / npm)の表示、または
`uv pip list` / `npm ls` で導入したパッケージのメタデータを参照してください。)

---

## 1. AprilTag タグ画像 (tag36h11)

- 該当ファイル: `scripts/apriltag_imgs/tag36h11/`、`frontend/public/tags/`
- 取得元: https://github.com/AprilRobotics/apriltag-imgs
- ライセンス: BSD 2-Clause License

```
BSD 2-Clause License

Copyright (c) 2013-2016, The Regents of The University of Michigan.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

---

## 2. Pyxel 固定ランタイム

- 該当ファイル: `pyxel_app/runtime/`(`pyxel.js`、`pyxel.css`、`import_hook.py`、
  `images/`、`pyxel-3.0.0-cp311-abi3-emscripten_5_0_3_wasm32.whl`)
- 取得元: https://github.com/kitao/pyxel (`cube` ブランチ @ f731329 をビルド。詳細は
  `pyxel_app/runtime/VERSION.md`)
- ライセンス: MIT License

```
MIT License

Copyright (c) 2018-2026 Takashi Kitao

This license applies to Pyxel - https://github.com/kitao/pyxel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

なお `pyxel_app/runtime/images/` に含まれる Pyxel のロゴ画像は起動画面の表示に必要な
ランタイムの一部として同梱しているものです。ロゴを Pyxel 以外の対象を指す目的で
使用することはできません。

#### wheel が静的リンクしている Rust クレートについて

同梱の wheel は Pyxel の Rust 実装をビルドしたバイナリで、多数の Rust クレートを
静的リンクしています。内訳は wheel 内の CycloneDX SBOM に記録されています。

- SBOM の位置: wheel 内 `pyxel-3.0.0.dist-info/sboms/pyxel-binding.cyclonedx.json`
- コンポーネント数: 201
- 含まれるライセンス: `MIT OR Apache-2.0`(112)、`MIT`(33)、**`MPL-2.0`(15)**、
  `Apache-2.0 OR MIT`(8)、`BSD-3-Clause`(5)、`BSD-2-Clause`(3)、`Apache-2.0`(3)、
  `Zlib`(2)、`ISC`(1)、`Apache-2.0 WITH LLVM-exception`(1)、
  `(MIT OR Apache-2.0) AND Unicode-3.0`(1) ほか

このうち **MPL-2.0** のクレートは音声デコーダ群と `option-ext` です。MPL-2.0 は
当該ファイルのソース入手可能性を求めるため、対象クレートを明示します。

| クレート | バージョン | ソース |
|---|---|---|
| `symphonia` および `symphonia-*`(core / common / metadata、bundle-flac / bundle-mp3、codec-aac / codec-adpcm / codec-alac / codec-pcm / codec-vorbis、format-mkv / format-ogg / format-riff) 計 14 | 0.6.0 | https://github.com/pdeljanov/Symphonia |
| `option-ext` | 0.2.0 | https://github.com/soc/option-ext |

各クレートのソースは上記および crates.io (`https://crates.io/crates/<name>/<version>`)
から入手できます。Hanoi Cube はこれらのクレートを改変していません。

---

## 3. M+ BITMAP FONTS (日本語ビットマップフォント)

- 該当ファイル: `pyxel_app/assets/umplus_j10r.bdf`
- 取得元: M+ FONTS PROJECT(Pyxel 同梱の `examples/assets` から複製)
- ライセンス: 以下のとおり(原文は `pyxel_app/assets/LICENSE_umplus_j10r.txt`)

```
umplus_j10r.bdf は M+ BITMAP FONTS(M+ FONTS PROJECT)の 10px 版を Unicode(iso10646-1)に
再構成したものです(Pyxel 同梱の examples/assets から複製)。ライセンスは以下(原文 LICENSE_E)。

M+ BITMAP FONTS                         Copyright 2002-2005  COZ <coz@users.sourceforge.jp>

-

LICENSE_E

These fonts are free software.
Unlimited permission is granted to use, copy, and distribute them, with
or without modification, either commercially or noncommercially.
THESE FONTS ARE PROVIDED "AS IS" WITHOUT WARRANTY.

http://mplus-fonts.sourceforge.jp/
```

---

## 4. Vite プロジェクトテンプレート (React + TypeScript)

- 該当ファイル: `frontend/README.md`
- 取得元: https://github.com/vitejs/vite (`packages/create-vite/template-react-ts`)
- ライセンス: MIT License

`create-vite` の React + TypeScript テンプレートが生成した README を、フロントエンドの
足場を作った際からそのまま残しているものです。

```
MIT License

Copyright (c) 2019-present, VoidZero Inc. and Vite contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
