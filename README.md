# Morning Shower Enforcer (朝シャワー強制ギプスアプリ)

本アプリケーションは、毎朝指定の時間（デフォルト 6:00 AM）までにシャワーを浴びたことをWebカメラと画像処理（OpenCV）で証明できない場合、PayPal経由で自動的に罰金（決済）を科す強制力のあるPythonアプリケーションです。

---

## 📁 ディレクトリ・ファイル構成

```
morning-shower-enforcer/
├── .env.example            # 環境変数のテンプレート
├── app.py                  # Streamlit UI & バックグラウンド監視スレッド
├── detector.py             # OpenCVを用いた濡れ髪判定ロジック
├── paypal_client.py        # PayPal REST API 連携クライアント
└── requirements.txt        # 必要なPythonパッケージ一覧
```

---

## 🚀 導入手順

### 1. リポジトリの準備と依存パッケージのインストール

1. ターミナルまたはPowerShellを開き、アプリケーションディレクトリに移動します。
2. 仮想環境を作成し、有効化します。
   ```bash
   python -m venv venv
   # Windowsの場合:
   venv\Scripts\activate
   # Mac/Linuxの場合:
   source venv/bin/activate
   ```
3. 必要なパッケージをインストールします。
   ```bash
   pip install -r requirements.txt
   ```

### 2. 環境変数の設定

1. `.env.example` をコピーして `.env` ファイルを作成します。
   ```bash
   copy .env.example .env
   ```
2. `.env` を開き、必要なパラメータを設定します（詳細は後述のPayPal設定を参照）。
   - `PAYPAL_CLIENT_ID`
   - `PAYPAL_CLIENT_SECRET`
   - `FINE_AMOUNT` (罰金額、例: `5.00`)
   - `FINE_CURRENCY` (通貨コード、例: `USD` または `JPY`)
   - `SHOWER_DEADLINE` (判定期限、例: `06:00`)

---

## 📸 OpenCV 濡れ髪判定の仕組みとキャリブレーション

髪の色、肌のトーン、部屋の照明条件は個人によって異なるため、本アプリでは**「キャリブレーション（事前登録）方式」**を採用しています。

1. **キャリブレーション**:
   - アプリ起動後、髪が**完全に乾いている状態**でカメラの前に立ち、撮影して「`Save as Dry Baseline (Calibrate)`」をクリックします。
   - 顔検出（Haar Cascade）により顔の上部を「髪の毛領域 (Hair ROI)」として切り出し、**平均輝度（明るさ）**と**ラプラシアン分散（テクスチャの細かさ）**を測定して `calibration.json` に保存します。
2. **濡れ髪判定のアルゴリズム**:
   - **明度の低下**: 髪が濡れると光の反射率が下がり、全体的に暗くなります（基準輝度の88%未満に低下したかをチェック）。
   - **テクスチャの平滑化（束感）**: 乾いた髪は髪の毛1本1本の境界（高周波エッジ）が多くありますが、濡れると束になって固まり、表面の細かい凹凸が減少します。ラプラシアンフィルタによるエッジ分散値を計算し、基準値の75%未満に低下したかをチェックします。
   - 上記のいずれか（または両方）の基準を満たした場合に「シャワー完了」と判定されます。

---

## 💳 PayPal API Sandbox環境でのテスト方法

本アプリでは、PayPalの **Orders API (v2)** を使用して決済要求をシミュレートします。

### 1. PayPal Developerアカウントの取得とアプリ作成
1. [PayPal Developer Portal](https://developer.paypal.com/) にアクセスし、個人のPayPalアカウントでログインします。
2. 左メニューの **Apps & Credentials** を選択し、**Sandbox** モードになっていることを確認して「**Create App**」をクリックします。
3. アプリ名（例: `ShowerEnforcer`）を入力し、アプリを作成します。
4. 生成された **Client ID** と **Secret** をコピーし、`.env` ファイルの `PAYPAL_CLIENT_ID` と `PAYPAL_CLIENT_SECRET` に貼り付けます。

### 2. テスト用 Sandbox アカウントの確認
PayPalが自動的にテスト用の「買い手（Personal）」と「売り手（Business）」のアカウントを作成してくれています。
1. Developer Portal の左メニューから **Testing** -> **Sandbox Accounts** を開きます。
2. 以下の2つのアカウントのメールアドレスとパスワードを確認（または編集）します。
   - **Business アカウント**: クレジットカード決済や売上を受け取るマーチャント（アプリ運営者側）
   - **Personal アカウント**: 罰金を支払うユーザー（あなた自身）

### 3. アプリケーションでの決済テストの流れ
1. **アプリ起動**:
   ```bash
   streamlit run app.py
   ```
2. **デモ決済の実行**:
   - 画面最下部の「`🛠️ Testing & Debug Controls`」を展開します。
   - 「`Force Trigger PayPal Fine immediately`」をクリックすると、PayPal APIへのリクエストが走り、Sandbox上に注文（Order）が作成されます。
3. **ユーザーによる承認（Sandbox）**:
   - アプリ上に「`👉 Click here to login & approve the fine in Sandbox`」というリンクが表示されます。
   - このリンクを開き、**Sandbox Personal アカウント**のメールアドレスとパスワードでログインして、支払いを承認（Approve）します。
4. **決済の確定 (Capture)**:
   - 承認後、アプリのデバッグパネルに表示されている「`Complete Payment Capture`」ボタンをクリックします。これにより、売り手のアカウントに実際に資金が移動する「キャプチャ処理」が完了し、決済が完了（`COMPLETED`）ステータスになります。

> [!IMPORTANT]
> **完全自動化（ユーザーの操作なしの自動課金）について**
> 実際のプロダクション環境や、完全自動化された罰金システム（毎朝6時にユーザーの操作を介さずにクレジットカード等から引き落とす）を実装するには、PayPalの **Reference Transactions（参照取引）** または **Vaulting API（決済情報の保存）** の承認をPayPalに申請し、有効化する必要があります。
> 有効化された後は、初回のセットアップ時にユーザーに「Billing Agreement（請求合意）」を結んでもらうことで、次回以降はアプリ側から任意のタイミングで自動的に課金（バックグラウンドキャプチャ）を実行できるようになります。

---

## 🌐 Gemini AI による高精度な判定モード

本アプリは、Googleのマルチモーダル生成AIである **Gemini API** を使用した高精度な濡れ髪判定に対応しています。

### 1. API キーの取得と設定
1. [Google AI Studio](https://aistudio.google.com/) にアクセスし、Googleアカウントでログインします。
2. 「**Get API key**」をクリックして、新しいAPIキーを作成します。
3. コピーしたキーを `.env` ファイルの `GEMINI_API_KEY` に設定します。
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```

### 2. 動作仕様
- **Gemini AIモード (自動検知)**:
  `.env` ファイルに有効な `GEMINI_API_KEY` が設定されており、且つ `google-genai` パッケージがインストールされている場合、アプリ起動時に自動的に「Gemini AIモード」が有効になります。
  このモードでは、ユーザーの乾いた髪の毛の事前登録（キャリブレーション）は**不要**です。AI（`gemini-2.5-flash` モデル）が画像全体の文脈から「髪の毛が濡れているか（シャワーを浴びた直後か）」をマルチモーダル解析し、判定とその根拠となる解説を返します。
- **ローカル OpenCVモード (フォールバック)**:
  APIキーが未設定である、または通信エラーが発生した場合は、自動的に従来の「OpenCVによる輝度・テクスチャ比較モード」にフォールバックします（このモードでは事前に乾いた髪のキャリブレーションが必要です）。

