"""
初回セットアップ用スクリプト
トークンの動作確認とユーザーIDを取得します
"""
import requests

print("=== sorane-threads-bot セットアップ ===\n")

token = input("アクセストークン（Meta Developerでコピーしたもの）: ").strip()

print("\nトークンを確認中...")

# ユーザーID取得
res = requests.get(
    "https://graph.threads.net/v1.0/me",
    params={"fields": "id,username", "access_token": token}
)
data = res.json()

if "id" not in data:
    print(f"\nエラー: {data}")
    print("\nMeta Developerで新しいトークンを生成し直してください。")
    exit(1)

user_id = data["id"]
username = data.get("username", "")

print(f"成功！ユーザー: @{username}、ID: {user_id}")

print("\n" + "="*50)
print("GitHubのSecretsに以下を登録してください：")
print("="*50)
print(f"\nTHREADS_ACCESS_TOKEN:\n{token}")
print(f"\nTHREADS_USER_ID:\n{user_id}")
print("\n" + "="*50)
