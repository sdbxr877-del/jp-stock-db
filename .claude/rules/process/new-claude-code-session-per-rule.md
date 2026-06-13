---
rule_id: process-new-claude-code-session-per-rule
category: process
priority: critical
paths: []
related_failures:
  - "失敗58"
related_rules:
  - "process-powershell-absolute-path (失敗56・環境境界管理の対)"
  - "process-handoff-disk-tracked-distinction (失敗55)"
  - "git-single-responsibility-commit (§9-2・1ルール=1commit と対応)"
  - "db_v0.15 追加原則 #1 (Web Claude 残量: 1セッション2〜3ルール上限)"
last_updated: 2026-06-13
applies_to_environments:
  - chat_claude
  - claude_code
  - human
---

# 1ルール = 新規 Claude Code セッション 1回 必須ルール

## 規範

ルールファイル(`.claude/rules/**/*.md`)を案 A ハイブリッドで作成する際は、**1ルールの作成につき新規 Claude Code セッションを 1回起動**すること。以下を禁止する:

1. **同一 Claude Code セッションで複数ルールの content を連続 Write**(前ルールの context を保持したまま次ルールへ進む)
2. **Web Claude が Phase 2 プロンプトに「セッション継続利用可」の選択肢を提示**すること
3. **1ルール commit 完了後にセッションを閉じず、同セッションで次ルールの cp/検証を継続**すること
4. **context 残量を確認せず「まだ入るだろう」と推測で同一セッションを使い回す**こと

本ルールは失敗58(同一 Claude Code セッションでルール content を連続 Write した結果、`Usage credits are required for long context requests` エラーで停止した事故)の再発防止規範である。`git-single-responsibility-commit`(§9-2・1ルール=1commit)の「セッション粒度版」にあたり、両者は「1ルール = 1セッション(作業)= 1commit(成果)」という一貫した粒度を構成する。

### なぜ 1ルール = 1セッションが必須か(技術的根拠: long context tier)

Claude Code セッションは、起動後に読み込んだ前提ファイル・送信プロンプト・往復のやり取り・検証出力・完了報告を**すべて context に累積保持**する。1ルール完了時点で、その累積は概ね以下を含む:

- 前提読込ファイル(CLAUDE.md / handoff 等・複数 KB)
- Phase 2 プロンプト(ルール content 本文を含む・数 KB〜10 KB)
- 検証スクリプトの生成・実行・出力
- 訂正の往復(SR-12 違反停止と再指示等が発生すれば加算)
- Phase 0-4 自己検証の全報告

ここに**次ルールの content(さらに 10 KB 級)+ 周辺指示**を足すと、long context tier(200K)を超過し、課金要件エラーで停止する。失敗58 はまさにこの累積超過だった。**ルールごとにセッションを新規起動すれば context はリセットされ、累積超過は構造的に起こらない**。

### context 累積の構造(本リポジトリ固有)

本プロジェクトのルール content は統一形式(frontmatter 8キー + 本体6セクション)で 1ファイル 10〜15 KB に達する。さらに検証は SHA-256 三点照合・frontmatter 検査を伴い、Claude Code 側の出力も相応に大きい。この「重い 1ルール」を複数回ぶん同一 context に積むと容易に上限へ届く。content が軽量なら同一セッションで足りる可能性はあるが、**本リポジトリのルール粒度では 1ルール = 1セッションが安全側の唯一の運用**である。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | 案 A ハイブリッドでの全ルール content の cp / 自己検証セッション |
| 必須 | Web Claude が設計する Phase 2 プロンプト(継続提案を含めない) |
| 必須 | Hiroyuki のセッション起動操作(ルールごとに新規起動) |
| 対象外 | ルールに紐づかない単発の軽量作業(ただし複数ルールにまたがる場合は本ルール準用) |

### 例外条項

| 例外 | 条件 |
|---|---|
| content が極小かつ検証込みで context に余裕が明確な場合 | 残量を実測・確認できる場合に限る。本リポジトリの標準ルール(10 KB 級)は非該当 |
| ルール作成以外の単発タスク | 1ファイルの軽微編集等、累積が問題にならない作業 |

### 主要パラメータ(本ルール作成時点)

| 項目 | 値 |
|---|---|
| long context tier 閾値 | 200K(超過で課金要件エラー) |
| 標準ルール content サイズ | 10〜15 KB / ファイル |
| 失敗58 発生箇所 | 第2ルール Phase 2 起動時(第1ルール完了直後の同一セッション) |
| Web Claude 側の対原則 | db_v0.15 追加原則 #1(1セッション 2〜3ルール + handoff が上限) |

## 違反パターン(検出すべき運用)

### Pattern 1: 同一セッションで複数ルール content を連続 Write(失敗58 の原型)

```
[同一 Claude Code セッション]
第1ルール: cp + Phase 0-4 検証 + 完了報告   ← context 累積
第2ルール: Phase 2 プロンプト送信           ← "Usage credits are required for long context requests" で停止
```
→ 第1ルールの累積に第2ルール content を足して 200K 超過。失敗58 の直接原因。

### Pattern 2: Web Claude が「セッション継続利用可」を提案(真因側)

```
（Web Claude の Phase 2 プロンプト・違反例）
「第1ルールと同じセッションを継続利用しても構いません。続けて第2ルールを…」
```
→ 提案自体が失敗58 を誘発する。Web Claude は継続利用の選択肢を出してはならない(責任所在側の対策)。

### Pattern 3: 完了後にセッションを閉じず継続

```
第1ルール commit 完了 → 同じ Claude Code 画面のまま第2ルールの cp を依頼
```
→ commit したからといって context はリセットされない。新規起動が必要。

### Pattern 4: 残量を推測で使い回す

```
「まだ context に余裕がありそうだから、このまま次のルールも」
```
→ 残量は推測対象ではない(§1.6「Success を信じない」の運用版)。安全側=新規セッション。

## 正しい実装パターン

### Pattern A: 1ルール = 新規セッション 1回(標準経路)

```
第1ルール: 新規セッション起動 → cp + 検証 → 報告 → セッション終了
第2ルール: 新規セッション起動(context リセット)→ cp + 検証 → 報告 → セッション終了
第3ルール: 新規セッション起動 → …
```
→ 各ルールが独立 context で完結。累積超過が構造的に発生しない。

### Pattern B: Web Claude の Phase 2 プロンプトは継続提案を含めない

```
（正しい Phase 2 プロンプト冒頭）
「新規 Claude Code セッション(失敗58・1ルール1セッション)。verbatim コピー + 自己検証のみ。」
```
→ プロンプト冒頭で「新規セッション」を明示し、継続利用の余地を残さない。本ルールの設計意図そのもの。

### Pattern C: ルール境界でセッションを明示的に区切る

```
1ルール完了報告を受領 → Hiroyuki が Claude Code セッションを終了/新規起動 → 次ルールへ
```
→ commit(PowerShell 側)とセッション終了をルール境界として揃える。§9-2(1commit)と粒度一致。

## 関連過去教訓

### 失敗58 の出自(handoff_db_v14 §4)

失敗58 は db_v0.14 第2ルール Phase 2 起動時に発見。第1ルール完了時点で Claude Code セッションが前提4ファイル + Phase 2 プロンプト(content 約 7.2 KB)+ SR-12 違反停止と再指示の往復 + 検証出力 + 完了報告を全保持しており、そこへ第2ルール content(約 9.5 KB)+ 周辺指示を追加した結果 200K tier を超過、`Usage credits are required for long context requests` で停止した。対策として「ルール1個作成 = 新規 Claude Code セッション1回(例外なし)」を原則化し、第3ルールでは新規セッション起動により再発なし。責任所在は Web Claude(第2ルール Phase 2 で「セッション継続利用可」を提案したミス)と記録されている。

### Web Claude 側の対(db_v0.15 追加原則 #1)

失敗58 は Claude Code 側の context 上限だが、Web Claude 側にも対の上限がある。db_v0.15 追加原則 #1「1セッション 2〜3ルール + handoff が上限」は、Web Claude(設計側)の残量管理規律であり、失敗58(Claude Code 実行側)の Web Claude 版にあたる。両者は「設計側・実行側それぞれの context 上限を超えない」という同一原理の表裏。

### 関連ルール

- `git-single-responsibility-commit`(§9-2): 「1ルール = 1commit」と「1ルール = 1セッション」が対応し、レビュー可能性と巻き戻し容易性を担保
- `process-powershell-absolute-path`(失敗56): 新規ウィンドウ/セッションの境界管理という同型の規律(cwd 検算 vs context リセット)
- `process-handoff-disk-tracked-distinction`(失敗55): セッション境界をまたぐ状態記載の正確性を支える

## レビュー時のチェックリスト

- [ ] 1ルールの cp / 検証ごとに新規 Claude Code セッションを起動しているか
- [ ] Web Claude の Phase 2 プロンプトに「セッション継続利用可」の文言がないか
- [ ] Phase 2 プロンプト冒頭で「新規セッション(失敗58)」を明示しているか
- [ ] 前ルール完了後、同一セッションのまま次ルールへ進んでいないか
- [ ] context 残量を「推測」で使い回していないか(安全側=新規起動)
- [ ] セッション境界が commit 境界(§9-2・1ルール=1commit)と揃っているか
- [ ] Web Claude 側も db_v0.15 #1(2〜3ルール上限)を守っているか

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 観点 | 関連ルール | 関係 |
|---|---|---|
| 作業粒度の一致 | `git-single-responsibility-commit` | 1ルール=1セッション=1commit |
| 境界管理の規律 | `process-powershell-absolute-path` | ウィンドウ cwd vs セッション context |
| 設計側の残量上限 | db_v0.15 追加原則 #1 | 失敗58 の Web Claude 版 |
| 推測排除 | §1.6「Success を信じない」 | 残量も推測せず安全側 |

### 運用上の同型箇所(レビュー対象候補)

- Web Claude の Phase 2 プロンプト雛形: 「新規セッション」明示と継続提案の不在
- セッション末の handoff: 残りルール数と Web Claude 残量(db_v0.15 #1)の整合
- Claude Code 完了報告の直後: セッション終了 → 新規起動の境界が守られているか
