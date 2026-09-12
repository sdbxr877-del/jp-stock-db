---
rule_id: general-attribute-errors-correctly
category: general
priority: critical
paths: []
related_failures:
  - "CW-05"
related_rules:
  - "general/dont-trust-success"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: cw-auto-collector
vault_version: 1.0
vault_status: active
vault_imported: 2026-08-31
last_updated: 2026-08-31
---

# エラーの帰責先を確かめてから集計・自動処置につなげる

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

エラーを**自分側の原因**と**相手側の原因**に切り分けずに、カウンタへ加算したり、
自動的な処置（停止・ブロック・除外・リトライ打ち切り）につなげてはならない。

[[CW-05]] では Resend（メール配信）の**自分の設定エラー**を、
**宛先のバウンス**として数えていた。3回で正当なアドレスが恒久停止されるところだった。
自分のミスの代償を相手に払わせる形になっており、**気づけないまま実害だけが出る**類型である。

原則: **自分の設定ミスを相手のせいにしない。** 切り分けられないなら、
「不明」として別カウンタに積み、自動処置の対象から外す。

## 違反パターン(検出すべきコード)

### Pattern 1: 例外を一括で相手起因として計上
```python
# 違反例
try:
    send(to=addr)
except Exception:
    bounce_count[addr] += 1        # API キー誤り・送信元未認証も bounce になる
    if bounce_count[addr] >= 3:
        suppress(addr)             # 正当なアドレスが恒久停止される
```

### Pattern 2: HTTP ステータスを見ずにリトライ打ち切り
```python
# 違反例: 401/403（自分の認証ミス）も 5xx（相手側）も同じ扱い
if attempts >= 3:
    mark_dead(target)
```

### Pattern 3: 「失敗率」に自分起因を混ぜて閾値判定
```python
# 違反例: 設定ミスで全件失敗している時に「相手が悪い」と結論できてしまう
if fail_rate > 0.5:
    disable_source(src)
```

## 正しい実装パターン

```python
OWN_FAULT = {400, 401, 403, 422}     # 認証・設定・リクエスト不正 = こちらの問題
PEER_FAULT = {450, 550}              # 宛先不明・受信拒否 = 相手側

def record(addr: str, status: int) -> None:
    if status in OWN_FAULT:
        own_error[status] += 1
        log.error("自分側の設定エラー status=%s。相手に計上しない", status)
        raise ConfigError(status)          # 気づける形で止める
    if status in PEER_FAULT:
        bounce_count[addr] += 1
        if bounce_count[addr] >= 3:
            suppress(addr)
        return
    unknown[addr] += 1                     # 切り分け不能は自動処置の対象外
```

**自動処置の前に必ず問う: この失敗は、相手が何もしなくても自分だけで直せるか。
直せるなら自分の問題であり、相手に計上してはならない。**

## レビュー時のチェックリスト

- [ ] `except Exception` で相手起因のカウンタを増やしていないか
- [ ] HTTP 4xx（自分起因）と 5xx / SMTP 5xx（相手起因）を区別しているか
- [ ] 切り分け不能なケースを「不明」として自動処置から除外しているか
- [ ] 自分起因のエラーが**気づける形で止まる**か（黙ってカウントされていないか）
- [ ] 恒久的な処置（suppress / block / disable）の前に、直近の失敗の内訳を確認しているか
