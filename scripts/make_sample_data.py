"""ダミーデータ生成スクリプト。社内文書風のテキストファイルと質問セットを作る。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

SAMPLE_DIR = ROOT / "data" / "sample"


def make_docs() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    # 社内規程文書風
    (SAMPLE_DIR / "経費規程_v3.txt").write_text("""\
経費精算規程（第3版）

第1条（目的）
本規程は、従業員が業務上要した費用の精算手続きを定めることを目的とする。

第2条（精算上限）
交通費: 1回につき上限10,000円
宿泊費: 1泊につき上限15,000円（東京・大阪・名古屋は20,000円）
接待交際費: 1件につき上限50,000円（部長承認が必要）

第3条（申請期限）
費用発生から30日以内に申請すること。期限超過は原則不受理。

第4条（領収書）
5,000円以上の費用は必ず領収書を添付すること。
""", encoding="utf-8")

    # 製品仕様書風
    (SAMPLE_DIR / "製品仕様書_ModelX.txt").write_text("""\
製品仕様書 - Model X Pro

【基本スペック】
- 重量: 1.2kg
- サイズ: 300mm × 200mm × 15mm
- バッテリー駆動時間: 最大18時間
- CPU: 第13世代インテルCore i7
- メモリ: 16GB LPDDR5
- ストレージ: 512GB NVMe SSD

【対応OS】
Windows 11 Home / Pro

【保証期間】
購入日から1年間（自然故障のみ）

【価格】
標準モデル: 198,000円（税込）
""", encoding="utf-8")

    # 会議議事録風
    (SAMPLE_DIR / "議事録_2026Q2戦略会議.txt").write_text("""\
Q2戦略会議 議事録

日時: 2026年4月15日 14:00-16:00
参加者: 田中部長、佐藤課長、鈴木、山田、渡辺

【議題1: 新規顧客獲得目標】
- Q2目標: 新規顧客50社（前年比20%増）
- 重点ターゲット: 製造業・小売業
- 施策: ウェビナー月2回開催、展示会2件出展

【議題2: 製品ロードマップ】
- 7月: Model X Pro リリース予定
- 9月: APIv2 公開予定
- Q3末までに機械学習機能を追加する方針を決定

【次回】2026年5月13日
""", encoding="utf-8")

    # 売上データ風 CSV
    (SAMPLE_DIR / "売上データ_2026Q1.csv").write_text("""\
月,製品,売上（万円）,販売数
1月,Model A,1200,48
1月,Model B,800,32
2月,Model A,1350,54
2月,Model B,750,30
3月,Model A,1500,60
3月,Model B,900,36
""", encoding="utf-8")

    # FAQ文書
    (SAMPLE_DIR / "FAQ_社内システム.txt").write_text("""\
社内システムよくある質問

Q: パスワードを忘れた場合は？
A: IT部門（内線3000）またはhelpdesk@example.comに連絡してください。
   対応時間は平日9:00-18:00です。

Q: VPN接続できない場合は？
A: まずVPNクライアントを最新版にアップデートしてください。
   それでも解決しない場合はITヘルプデスクへ。

Q: 社内Wikiのアカウントはどうやって作る？
A: 入社後、人事から招待メールが届きます。届かない場合は人事部（内線2000）へ。

Q: リモートワーク申請の締め切りは？
A: 前週金曜日の17:00までに申請システムから申請してください。
""", encoding="utf-8")

    print(f"サンプル文書 {len(list(SAMPLE_DIR.glob('*')))} 件を作成: {SAMPLE_DIR}")


def make_questions() -> None:
    questions = [
        {"id": "q001", "question": "宿泊費の精算上限はいくらですか？", "answer": "1泊につき上限15,000円（東京・大阪・名古屋は20,000円）"},
        {"id": "q002", "question": "接待交際費の申請に誰の承認が必要ですか？", "answer": "部長承認が必要"},
        {"id": "q003", "question": "Model X Proのバッテリー駆動時間を教えてください", "answer": "最大18時間"},
        {"id": "q004", "question": "Q2の新規顧客獲得目標は何社ですか？", "answer": "50社（前年比20%増）"},
        {"id": "q005", "question": "3月のModel Aの売上はいくらですか？", "answer": "1500万円"},
        {"id": "q006", "question": "パスワードを忘れた場合のIT部門の内線番号は？", "answer": "3000"},
        {"id": "q007", "question": "リモートワークの申請締め切りはいつですか？", "answer": "前週金曜日の17:00"},
        {"id": "q008", "question": "APIv2の公開予定はいつですか？", "answer": "9月"},
        {"id": "q009", "question": "社内WifiのパスワードはABCですか？", "answer": "わかりません（文書に記載なし）"},
        {"id": "q010", "question": "Model X Proの価格はいくらですか？", "answer": "198,000円（税込）"},
    ]

    out_path = SAMPLE_DIR / "questions.json"
    out_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2))
    print(f"サンプル質問 {len(questions)} 件を作成: {out_path}")


if __name__ == "__main__":
    make_docs()
    make_questions()
