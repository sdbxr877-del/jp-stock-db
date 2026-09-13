# formula_inventory_v1 — 外部2プロジェクト計算式の棚卸し（P8 融合フェーズ用ドラフト）

出典:
- App1 = `App1_screening_V9` … TGS スクリーニングエンジン（母集団スキャン・6軸スコア）
- App2 = `App2_V4` … 個別銘柄分析（テクニカルチャート＋同 TGS）

充足度凡例（現 jp_stock_db 基準・v57/P3 実測後）:
- ◎ = 即実装可（既存データで VIEW 化できる）
- ○ = データは有り・ロジック定義が要る
- △ = 要データ追加（§A 自動取得の新規列/系列）
- × = 手動入力（§B）or 外部キュレーション

前提データ源: `raw.prices`(date/close/volume/adj_close, PARTITION date) / `raw.financials`(revenue/op_profit/net_income/eps/roe ＋P3で equity/shares_outstanding/dividend_paid) / `raw.tickers`(market/sector) / `analytics.*`。

---

## 1. ファンダメンタル指標

| 式名 | 計算式（原典） | 必要入力 | 充足度 | jp_stock_db での実装メモ |
|---|---|---|---|---|
| 売上成長率 | (当期売上−前期売上)/前期売上×100 | revenue 2期 | ◎ | financials を ticker×reported_at で前期 LAG |
| EPS成長率 | (当期EPS−前期EPS)/前期EPS×100 | eps 2期 | ◎ | 同上 LAG |
| 売上CAGR(3年) | (最新売上/3年前売上)^(1/3)−1 | revenue 4期 | ◎ | financials 期系列 |
| ROE | 純利益/自己資本×100 | net_income, equity | ◎ | financials.roe 既存 or P3 equity で再計算 |
| ROEトレンド | 過去3年 ROE の上昇/安定/低下 | roe 3期 | ◎ | LAG 判定ルール要定義 |
| PER | 株価/EPS（= 時価総額/純利益） | close, eps | ◎ | P3後 `25_capital_metrics` に統合可 |
| PBR | 株価/BPS（BPS=equity/shares） | close, equity, shares | ◎ | **P3 実装済**（25_） |
| 時価総額 | 株価×発行済株式数 | close, shares | ◎ | **P3 実装済**（25_） |
| DOE | 年間配当/自己資本×100 | dividend_paid, equity | ◎ | **P3 実装済**（25_・偽陰性要改善） |
| PEG | PER/EPS成長率 | PER, EPS成長率 | ◎ | 上記2式の合成 |
| PER拡大余地 | (業界平均PER/現PER−1)×100 | PER, sector | ○ | tickers.sector で業界中央PER集計→結合 |
| FCF利回り | FCF/時価総額×100, FCF=営業CF−設備投資 | 営業CF, capex | △ | **営業CF/capex 未取得**。yfinance cashflow に有→列追加(A項目) |
| 浮動株比率 | 浮動株数/発行済×100 | 浮動株数 | × | **浮動株数 未取得**。手動§B or 別ソース |

## 2. テクニカル指標（すべて `raw.prices` から算出）

| 式名 | 計算式（原典） | 必要入力 | 充足度 | 実装メモ |
|---|---|---|---|---|
| 移動平均(MA) | n日終値の単純平均 | close 系列 | ◎ | AVG OVER (ORDER BY date ROWS n) |
| RSI(14) | 100−100/(1+RS), RS=平均上昇/平均下落 | close 系列 | ◎ | 日次差分→14日窓 |
| MACD | EMA12−EMA26, signal=EMA9(MACD) | close 系列 | ◎ | EMA は再帰→SQLは近似 or UDF |
| VolumeSpike | 当日出来高/20日平均出来高 | volume 系列 | ◎ | volume / AVG OVER 20d |
| VWAP乖離 | \|現価−VWAP\|/VWAP×100 | 価格・出来高（日中） | ○ | 日足では (close, volume) 近似VWAP。真値は分足要 |
| Price Compression | 価格変動の収縮度 | close 系列 | ○ | 直近ボラ/長期ボラ 等の定義確定要 |
| Accum日数 | 出来高増＋価格横ばい＋VWAPタイトの継続日数 | volume, close | ○ | 複合条件の連続日数カウント（ルール定義要） |

## 3. 独自スコア（TGS エンジン・App1/App2 共通）

| 式名 | 計算式（原典） | 構成入力 | 充足度 | 実装メモ |
|---|---|---|---|---|
| G（成長） | min(売上成長率/30, 1.0) | 売上成長率 | ◎ | §1 から |
| M（市場サイズ） | clamp(log10(時価総額億/50)/2.5, 0.15, 1) | 時価総額 | ◎ | P3 mcap から |
| T（テーマ係数） | sector/comment を THEME_T 表に照合し最大値 | sector, テーマ表 | × | **テーマ→係数表は手動キュレーション（§B）** |
| InstScore | VolumeSpike×VWAP偏差スコア×Accum×PriceComp | テクニカル4種 | ○ | §2 の構成要素が揃えば合成可 |
| SmartMoney | min((VolumeSpike/max(価格変動,0.3))/scale, 1) | volume, price_change | ◎ | prices から |
| PER拡大スコア | 業界比 / 理論比(EPS成長×2) の正規化 | PER, 業界PER, EPS成長 | ○ | §1 PER拡大余地に依存 |
| TGSスコア | G×M×T×Inst×SM×PERの積 | 上記6軸 | ○ | T（手動）以外は充足 |
| テンバガー確率 | 100/(1+exp(−6×(score−0.03))) | TGSスコア | ◎ | ロジスティック変換 |
| フェーズ判定 | Seed→Accum→Makeup→Inst→Mania の5段階 | 複合 | ○ | 判定ルールの明文化要 |

## 4. 移植順序の提案（P8・P3クローズ後）

1. **即実装（◎）から VIEW 化**: 売上/EPS成長・CAGR・PER・PEG・PBR・時価総額・DOE・ROEトレンド → `26_fundamental_growth.sql` 等。P3 の `capital_metrics` を土台に拡張。
2. **テクニカル VIEW**（◎）: MA/RSI/VolumeSpike/SmartMoney → `27_technicals.sql`。MACD/EMA は SQL 近似か Python 前計算を判断。
3. **要ロジック定義（○）**: VWAP乖離・PriceComp・Accum日数・フェーズ判定 → 定義を明文化してから実装。
4. **要データ追加（△）**: 営業CF/capex（FCF用）→ financials に cashflow 由来列を追加（P3 と同型の列拡張）。
5. **手動（×）**: T テーマ係数表・浮動株比率・TAM → §B `manual_inputs` の器に載せる。

## 5. 検証方針（リグレッション）

App1/App2 が過去に出していた各銘柄のスコア（TGS/InstScore 等）を「正解」とし、jp_stock_db の VIEW 出力と同一銘柄・同一基準日で突合。差分が出た式は入力データ or 定義のズレを特定して是正（§1.6 精神）。特に近似が入る VWAP乖離・MACD・Accum日数は要注意。

## 6. 重要な設計原則（再掲）

- 計算式は必ず analytics 層（SQL VIEW）に置き、UI には一切埋めない。今後の UI は VIEW を読むだけ。
- 手動・キュレーション依存（T テーマ、浮動株、TAM）は §B に隔離し、自動算出式と混在させない。
- UI レイアウト（App1/App2 の HTML/CSS）は破棄。移植対象は計算ロジックのみ。

## 7. 実装後の追記（2026-09-12）

§2 のテクニカル指標は `jp-stock-db` 側で実装済み。本表作成時点（v57/P3）の「実装メモ」は
計画時点の想定であり、実際の実装は次の通り（詳細は `phase45_data_inventory.md` §F・
`handoff_db_v82.md` §1〜§2 を参照）:

- **RSI(14)**: `analytics/screening/sql/37_technicals_wilder.sql` → VIEW
  `analytics.technicals_wilder`.`rsi14_wilder`列。ワイルダー漸化式を250行打ち切りの
  `ARRAY_AGG`窓で近似実装（UDF不使用。三点照合の対象外資産を増やさない方針のため）。
  NULLになるのは「初日（前日終値なし）」と「窓内の値動きが完全にゼロの低流動性銘柄」の
  2パターンのみで、いずれもロジック欠陥ではなく上流データの実態。
- **MACD**: 同VIEWの`macd`/`macd_signal`/`macd_hist`列。EMA12・EMA26・signal（decay 0.8）を
  すべて同じ250行打ち切り近似で実装。全行で非NULL（欠損項は重みごと分母から除外して正規化）。
- **VolumeSpike**: `analytics/screening/sql/34_technicals.sql` → VIEW `analytics.technicals`.
  `vol_spike20`列（`volume / AVG(volume) OVER 20d`、想定どおりの実装）。同VIEWでATR14
  （単純移動平均・`atr14_sma`列）・MFI14・スローストキャス（`stoch_k_slow`/`stoch_d`）も実装済み
  （本表§2には行が無いが§C17として`phase45_data_inventory.md`側で管理）。
- VWAP乖離・Price Compression・Accum日数・フェーズ判定（○の行）はいずれも未実装のまま
  （ロジック定義が未確定のため）。
