---
rule_id: secrets-no-secret-in-url-params
category: secrets
priority: critical
paths:
  - "*.py"
  - "*.sh"
  - "*.ps1"
  - "*.yml"
related_failures: []
related_rules:
  - "project_rules_db_v1.md §5 (セキュリティルール: secrets は .env / Secrets 経由・Git 非コミット)"
  - "§3 G2 (Secrets ログ出力ゲート)"
  - "SR-9 (外部 API は公式仕様を web 確認)"
  - secrets-no-env-var-print
  - bq-staging-only-tests
last_updated: 2026-06-01
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# Secrets: 認証情報を URL クエリ・パスに直書き / ログ / commit しない

## 規範

API キー・トークン・パスワード等の秘匿情報を、**URL のクエリ文字列・パスへ「ハードコード」「ログ出力」「commit」しない**こと。認証は**ヘッダー方式を優先**する。以下を禁止する:

1. **f-string / 文字列連結での URL 直書き**(例: `url = f"...?Subscription-Key={key}"` のように secret を URL 文字列に埋め込む)
2. **組み立て済み URL の出力・記録**(`print(response.url)` / `logging` への URL 出力 / 例外メッセージへの URL 混入)— secret を含む URL がログ・標準出力・トレースバックに残る
3. **secret リテラルのソース直書き**(`API_KEY = "実値"` のハードコード・G2 / §5 と二重違反)
4. **curl コマンドの secret 込み残存**(`.sh` への secret 入り URL 記述 / ターミナルエコーの履歴・ログ残存)
5. **GHA workflow での secret 入り URL のエコー**(`echo` / `run` ログに secret を含む URL を出力)

本ルールは `project_rules_db_v1.md §5`(secrets は `.env` / GHA Secrets 経由で Git 非コミット)および `§3 G2`(Secrets ログ出力ゲート)を、**URL 経由の漏洩経路に特化して分解した詳細仕様**である。
固有の過去事故番号を持たない**予防的規範**であり、`related_failures` は空配列とする
(`secrets/no-env-var-print.md`(G2 / 失敗39 派生)/ git 系3ルールと同型の「事故記録なし予防ルール」)。

### なぜ URL 経由の漏洩が危険か

URL は「リクエストの宛先」であると同時に「あちこちに複製される文字列」である。secret をクエリに乗せると、以下の経路で**意図せず永続化**する:

- サーバ側アクセスログ / プロキシログ / CDN ログ
- ブラウザ履歴・referrer ヘッダー(第三者サイトへ転送され得る)
- アプリログ・例外トレースバック(`response.url` 経由)
- GitHub Actions の実行ログ(`echo`・`set -x`・エラー出力)
- shell 履歴(`.bash_history` 等)・`.sh` への commit

ヘッダー認証(`x-api-key` 等)はリクエストボディ/ヘッダーに乗るため、上記の複製経路の大半を回避できる。**漏洩面の広さがヘッダー方式と根本的に異なる**ため、URL クエリへの secret 配置を原則禁止とする。

### 本プロジェクトの API 認証方式(SR-9 で公式確認済)

| API | 認証方式 | URL 露出 | 本ルールでの扱い |
|---|---|---|---|
| yfinance | 認証なし | なし | 対象外 |
| J-Quants V2 | `x-api-key` **ヘッダー** | なし | 理想形(Pattern A) |
| EDINET API v2 | `Subscription-Key` **クエリパラメータ必須** | あり(仕様上不可避) | 例外条項 + 4 mitigation(Pattern B) |

J-Quants はヘッダー認証で URL 非露出。EDINET は公式仕様 Version2 で `Subscription-Key` をクエリパラメータに要求するため、URL に乗ること自体は仕様上不可避である(SR-9 で公式仕様を確認)。

### 例外条項(EDINET 型: 仕様上クエリパラメータ必須の API)

仕様上クエリパラメータでの key 送信が必須の API は、**以下 4 つの mitigation を全充足する場合に限り**許容する:

| # | mitigation | 内容 |
|---|---|---|
| 1 | env / Secrets 由来 | key は `os.getenv()` / GHA Secrets から取得。ソースへハードコードしない(G2 / §5) |
| 2 | params 辞書経由 | `requests.get(url, params={...})` で渡す。`f"...?key={k}"` の文字列 URL 構築をしない |
| 3 | 組立 URL を出力しない | `response.url` / 組立済み URL を print / log / 例外メッセージに出さない |
| 4 | GHA で URL をエコーしない | secret を含む URL を `echo` / ログ出力しない・`set -x` 時は該当行をマスク |

**データ収集への影響はゼロ**: `params={...}` 辞書経由でも、`requests` が生成するクエリ文字列・サーバへ届くリクエストは文字列 URL 直書きと**完全に同一**である。本 mitigation は「漏洩経路の遮断」だけを行い、リクエストの成否・取得結果には一切影響しない。

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| J-Quants 認証 | `x-api-key` ヘッダー | 既存 `jquants_update.py` / SR-9 確認 |
| EDINET 認証 | `Subscription-Key` クエリパラメータ | EDINET API 仕様書 Version2 / SR-9 確認 |
| key の保管 | `.env`(Git 非コミット)/ GHA Secrets | project_rules_db_v1.md §5 |
| G2 監査対象 | `print.*token|key|secret|password` | project_rules_db_v1.md §3 |

## 違反パターン(検出すべきコード)

### Pattern 1: f-string / 連結での URL 直書き(最頻出)

```python
# 違反例: secret を URL 文字列へ埋め込む
url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json?date={d}&Subscription-Key={api_key}"   # ❌
url = base + "?Subscription-Key=" + api_key                                                        # ❌ 連結も同型
```

→ 文字列化された URL がそのまま変数・ログ・例外に流れ、漏洩面が広がる。`params={...}` 辞書経由(Pattern B)に置換する。

### Pattern 2: 組み立て済み URL のログ出力(見落としやすい)

```python
# 違反例: params= を正しく使っても、URL をログ出力すると key が漏れる
resp = requests.get(url, params={"date": d, "Subscription-Key": api_key})
logging.info("requested: %s", resp.url)   # ❌ resp.url に secret 入りクエリが含まれる
raise RuntimeError(f"failed: {resp.url}")  # ❌ 例外メッセージにも secret が乗る
```

→ `params=` 利用でも `resp.url` を出力すれば漏洩する。URL は出さず、ステータスコードや `docID` 等の非機微値で記録する。

### Pattern 3: secret リテラルのソース直書き(G2 / §5 と二重違反)

```python
# 違反例: key をソースに直書き
API_KEY = "abcd1234efgh5678"     # ❌ §5(.env 経由)違反・ハードコード
```

→ ソース commit で secret が Git 履歴に永続化する。`os.getenv("EDINET_API_KEY")` に置換する。

### Pattern 4: curl コマンドの secret 込み残存(.sh / ログ)

```bash
# 違反例: secret 入り URL を .sh に記述 / ログへ出力
curl "https://api.edinet-fsa.go.jp/api/v2/documents.json?date=2024-05-17&Subscription-Key=abcd1234"   # ❌
```

→ `.sh` に commit されれば Git 履歴に、ターミナル実行なら shell 履歴・ログに secret が残る。

### Pattern 5: GHA workflow での secret 入り URL のエコー

```yaml
# 違反例: GHA run で secret を含む URL を出力
- run: echo "calling https://api.edinet-fsa.go.jp/...?Subscription-Key=${{ secrets.EDINET_API_KEY }}"   # ❌
```

→ GitHub Actions の実行ログは閲覧可能で、`echo` / `set -x` により secret が平文で残る(SR-17 の bash pre-flight 時も該当)。

## 正しい実装パターン

### Pattern A: ヘッダー認証(J-Quants・理想形)

```python
# ✅ 正しい例: secret はヘッダーに乗せ、URL に出さない
import os, requests
headers = {"x-api-key": os.getenv("JQUANTS_API_KEY")}
resp = requests.get("https://api.jquants.com/v2/prices/daily_quotes", headers=headers, params={"code": code})
resp.raise_for_status()
```

- key は `os.getenv()` 由来・ヘッダー送信で URL 非露出
- ログには `resp.status_code` 等の非機微値のみ

### Pattern B: params 辞書 + env(EDINET・例外条項の正規実装)

```python
# ✅ 正しい例: クエリ必須 API でも params 辞書 + env、URL は出力しない
import os, requests
api_key = os.getenv("EDINET_API_KEY")                       # mitigation 1: env 由来
url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
params = {"date": d, "type": 2, "Subscription-Key": api_key}  # mitigation 2: params 辞書経由
resp = requests.get(url, params=params)
resp.raise_for_status()
logging.info("EDINET ok: count=%s", resp.json()["metadata"]["resultset"]["count"])  # mitigation 3: URL を出さない
```

- 文字列 URL を組まず `params={...}` 辞書で渡す(送信されるリクエストは Pattern 1 と同一・収集結果不変)
- `resp.url` を print / log / 例外に出さない
- 記録は件数・`docID` 等の非機微値のみ

### Pattern C: GHA Secrets 経由(URL をエコーしない)

```yaml
# ✅ 正しい例: secret は env 経由でスクリプトへ渡し、URL を出力しない
- env:
    EDINET_API_KEY: ${{ secrets.EDINET_API_KEY }}
  run: python edinet_fetch.py        # スクリプト内で os.getenv + params 辞書(Pattern B)
```

- secret は `env:` 経由でプロセスへ渡し、`run` で URL をエコーしない
- `set -x` を使う場合は secret を含む行を出さない設計にする(SR-17 pre-flight でも確認)

### Pattern D: 漏洩経路の検証(commit 前)

```bash
# ✅ 正しい例: URL ログ出力・ハードコードの混入を機械検出
grep -nE 'resp(onse)?\.url' edinet_fetch.py     # response.url のログ出力経路を確認
grep -nE 'Subscription-Key=' edinet_fetch.py    # f-string / curl への直書きを確認(params 辞書なら hit しない)
```

- `response.url` のログ出力箇所をゼロにする
- `Subscription-Key=`(URL 直書き形)が hit したら Pattern B に置換(params 辞書は `"Subscription-Key":` の辞書キー形で、`=` 形には hit しない)

## 関連過去教訓

### §5 / G2 の URL 特化分解(事故記録なしの予防的規範)

- **位置づけ**: `project_rules_db_v1.md §5`(secrets は `.env` / Secrets 経由)と `§3 G2`(Secrets ログ出力ゲート)を、URL 経由の漏洩面に特化して分解
- **固有失敗番号**: なし(実害が発生する前に予防原則として確立)
- **本ルールとの関係**: `related_failures` は空配列(`no-env-var-print.md` / git 系3ルールと同型の誠実表現)

### SR-9(公式仕様確認)との連動

- **関係**: EDINET が `Subscription-Key` をクエリパラメータで要求することは SR-9 に従い公式仕様 Version2 で確認した。「URL に乗せるな」を単純絶対化せず、仕様の制約を正しく反映した例外条項を設計
- **本ルールとの関係**: 外部 API の認証方式は SR-9 で確認し、ヘッダー / クエリの別に応じて Pattern A / B を選ぶ

### no-env-var-print.md(G2)との連動

- **関係**: `no-env-var-print.md` は「変数名・値を print に直書きしない」、本ルールは「URL 経由で secret を出さない」。いずれも G2(Secrets ログ出力ゲート)の派生で、出力経路が異なる
- **本ルールとの関係**: 両者で G2 の漏洩経路(print 直書き / URL 出力)を網羅。双方向参照

### 関連ルール

- `project_rules_db_v1.md §5`: secrets は `.env` / GHA Secrets 経由で Git 非コミット(本ルールの SSOT)
- `project_rules_db_v1.md §3 G2`: Secrets ログ出力ゲート(URL 出力も漏洩経路)
- `SR-9`: 外部 API は公式仕様を web 確認(EDINET 認証方式の確認根拠)
- `secrets/no-env-var-print.md`: print 直書き禁止(本ルールと G2 派生で対)
- `bq/staging-only-tests.md`: 承認なし実行禁止(secret を扱う処理の慎重運用と同型)

## レビュー時のチェックリスト

- [ ] f-string / 連結で secret を URL 文字列に埋め込んでいないか確認した(`?key={k}` 形)
- [ ] `response.url` / 組立済み URL を print / log / 例外メッセージに出していないか確認した
- [ ] secret をソースにハードコードしていないか確認した(`os.getenv()` 由来か)
- [ ] ヘッダー認証が可能な API(J-Quants 等)でヘッダー方式を使っているか確認した
- [ ] クエリ必須 API(EDINET 等)で 4 mitigation(env / params 辞書 / URL 非出力 / GHA 非エコー)を全充足したか確認した
- [ ] `.sh` / ターミナル履歴に secret 入り curl URL が残っていないか確認した
- [ ] GHA workflow で secret を含む URL を `echo` / ログ出力していないか確認した(`set -x` 時のマスク含む)
- [ ] `grep -nE 'resp(onse)?\.url'` で URL ログ出力経路がゼロか確認した
- [ ] 新規外部 API 利用前に SR-9 で認証方式(ヘッダー / クエリ)を公式確認したか
- [ ] `.env` / 認証 JSON が `.gitignore` 対象で commit されていないか確認した(§5)

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連規範 | 参照ルール |
|---|---|---|
| secret を標準出力系に出さない | §3 G2 | `secrets/no-env-var-print.md` |
| 外部 API は公式仕様で確認してから実装 | SR-9 | （§ルール直参照） |
| 承認・検証なしで機微処理を確定させない | §9 原則 | `bq/staging-only-tests.md` |
| 出力前に漏洩経路を機械検出する | G2 | `secrets/no-env-var-print.md` |

これらは「**秘匿情報の漏洩経路を網羅的に塞ぎ、出力・記録・commit から secret を排除する**」という共通のリスク制御構造を持つ。

### コードベース内の同型箇所(レビュー対象候補)

| ファイル / 経路 | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| EDINET 取得スクリプト(`.py`) | `Subscription-Key` の URL 直書き / `resp.url` ログ | Pattern B / D 適用 |
| `jquants_update.py` | `x-api-key` ヘッダーの URL 露出 / ログ | Pattern A 維持の確認 |
| 全 `.sh`(将来の curl スクリプト) | secret 入り URL の記述・履歴残存 | Pattern 4 適用 |
| GHA workflow(`.yml`) | secret 入り URL の `echo` / `set -x` 露出 | Pattern 5 / C 適用 |
| 例外ハンドラ全般 | トレースバック・例外メッセージへの URL 混入 | Pattern 2 適用 |

新規の外部 API 取得経路を追加する際も本表に追記し、認証方式(ヘッダー / クエリ)に応じた Pattern 適用を判定すること。
