#!/bin/bash
# Raspberry Pi 自動セットアップスクリプト（anpi-watch）
# Usage: bash setup_auto.sh

# set -e

# 色付きログ用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Raspberry Pi セットアップ (anpi-watch)${NC}"
echo -e "${BLUE}========================================${NC}\n"

# ========================================
# Step 1: 必要な情報の入力
# ========================================
echo -e "${YELLOW}📝 Step 1: デバイス情報の入力${NC}\n"

read -p "Device ID (例: ito-raspi-01): " DEVICE_ID
read -p "S3 Bucket Name (例: anpi-watch-data): " S3_BUCKET
read -p "AWS Region [ap-northeast-1]: " REGION
REGION=${REGION:-ap-northeast-1}

echo ""
read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
read -sp "AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
echo ""

echo -e "\n${BLUE}確認:${NC}"
echo -e "  Device ID: ${DEVICE_ID}"
echo -e "  S3 Bucket: ${S3_BUCKET}"
echo -e "  Region:    ${REGION}"
echo -e "  Access Key ID: ${AWS_ACCESS_KEY_ID}"
echo ""

read -p "この内容でセットアップを開始しますか？ (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo -e "${RED}セットアップをキャンセルしました${NC}"
    exit 0
fi

# ========================================
# Step 2: 基本パッケージのインストール
# ========================================
echo -e "\n${YELLOW}📦 Step 2: 基本パッケージのインストール${NC}\n"

# vim-tinyを削除してvimをインストール
if dpkg -l | grep -q vim-tiny; then
    echo "Removing vim-tiny..."
    sudo apt-get remove --purge vim-tiny -y
fi

echo "Updating package list..."
sudo apt-get update -y

echo "Installing vim..."
sudo apt-get install vim -y

echo "Installing AWS CLI..."
sudo apt-get install awscli -y

echo -e "${GREEN}✓ パッケージのインストール完了${NC}\n"

# vim --version
aws --version

# ========================================
# Step 3: SSH設定（GitHub Deploy Key）
# ========================================
echo -e "\n${YELLOW}🔑 Step 3: GitHub Deploy Key の設定${NC}\n"

# SSHディレクトリ作成
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# SSH鍵生成（既存の鍵がない場合のみ）
if [ ! -f ~/.ssh/id_ed25519_github ]; then
    echo "Generating SSH key..."
    ssh-keygen -t ed25519 -C "raspi-anpi-watch" -f ~/.ssh/id_ed25519_github -N ""
    echo -e "${GREEN}✓ SSH鍵を生成しました${NC}\n"
else
    echo -e "${YELLOW}⚠️  SSH鍵は既に存在します${NC}\n"
fi

# SSH configファイルの作成
echo "Creating SSH config..."
cat > ~/.ssh/config <<EOF
Host github-anpi
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
EOF

chmod 600 ~/.ssh/config
echo -e "${GREEN}✓ SSH config を作成しました${NC}\n"

# 公開鍵を表示
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GitHub Deploy Key 登録手順${NC}"
echo -e "${BLUE}========================================${NC}\n"
echo "以下の公開鍵をGitHubのDeploy Keyに登録してください:"
echo ""
cat ~/.ssh/id_ed25519_github.pub
echo ""
echo -e "${YELLOW}登録URL: https://github.com/sumi-ito/anpi-watch/settings/keys/new${NC}"
echo ""
read -p "Deploy Keyの登録が完了したらEnterキーを押してください..."

# GitHub接続テスト
echo -e "\n${YELLOW}GitHub接続テスト中...${NC}"
if ssh -T github-anpi 2>&1 | grep -q "successfully authenticated"; then
    echo -e "${GREEN}✓ GitHub接続成功${NC}\n"
else
    echo -e "${RED}❌ GitHub接続に失敗しました${NC}"
    echo "Deploy Keyが正しく登録されているか確認してください"
    exit 1
fi

# ========================================
# Step 4: リポジトリのクローン
# ========================================
echo -e "\n${YELLOW}📥 Step 4: リポジトリのクローン${NC}\n"

cd ~

if [ -d ~/anpi-watch ]; then
    echo -e "${YELLOW}⚠️  anpi-watch ディレクトリは既に存在します${NC}"
    read -p "既存のディレクトリを削除して再クローンしますか？ (y/n): " RECLONE
    if [ "$RECLONE" = "y" ]; then
        rm -rf ~/anpi-watch
        git clone github-anpi:sumi-ito/anpi-watch.git
    else
        cd ~/anpi-watch
        git pull
    fi
else
    git clone github-anpi:sumi-ito/anpi-watch.git
fi

cd ~/anpi-watch
echo -e "${GREEN}✓ リポジトリの準備完了${NC}\n"

# ========================================
# Step 5: config.envの作成
# ========================================
echo -e "\n${YELLOW}⚙️  Step 5: config.env の作成${NC}\n"

# /etc/pir-monitor/ ディレクトリ作成
sudo mkdir -p /etc/pir-monitor/

# config.env作成
cat > ~/anpi-watch/pi/config.env <<EOF
# Device Configuration
DEVICE_ID="${DEVICE_ID}"
S3_BUCKET="${S3_BUCKET}"
REGION="${REGION}"

# AWS Credentials
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
AWS_DEFAULT_REGION="${REGION}"
EOF

# config.envを配置
sudo ln -s ~/anpi-watch/pi/config.env /etc/pir-monitor/config.env

echo -e "${GREEN}✓ config.env を作成しました${NC}\n"

# ========================================
# Step 6: AWS S3 接続テスト
# ========================================
echo -e "\n${YELLOW}🔍 Step 6: AWS S3 接続テスト${NC}\n"

# 環境変数を読み込み
source /etc/pir-monitor/config.env

# S3バケット存在確認
# echo "Checking S3 bucket: ${S3_BUCKET}..."
# if aws s3 ls "s3://${S3_BUCKET}/devices/${DEVICE_ID}" --region ${REGION} 2>/dev/null; then
#     echo -e "${GREEN}✓ S3バケットへのアクセス成功${NC}\n"
# else
#     echo -e "${RED}❌ S3バケットへのアクセスに失敗しました${NC}"
#     echo "以下を確認してください:"
#     echo "  1. バケット名: ${S3_BUCKET}"
#     echo "  2. AWS認証情報が正しいか"
#     echo "  3. IAMポリシーでS3アクセス権限があるか"
#     exit 1
# fi

# テストファイルのPUT
TEST_KEY="devices/${DEVICE_ID}/test/setup-$(date +%s).txt"
echo "Testing S3 PUT operation..."
echo "setup test" | aws s3 cp - "s3://${S3_BUCKET}/${TEST_KEY}" --region ${REGION}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ S3への書き込みテスト成功${NC}\n"
    # テストファイルを削除
    aws s3 rm "s3://${S3_BUCKET}/${TEST_KEY}" --region ${REGION} 2>/dev/null
else
    echo -e "${RED}❌ S3への書き込みに失敗しました${NC}"
    echo "IAMユーザーに以下の権限が必要です:"
    echo "  - s3:PutObject"
    echo "  - s3:GetObject"
    echo "  - s3:ListBucket"
    echo ""
    echo "必要なバケットポリシー例:"
    echo '{'
    echo '  "Version": "2012-10-17",'
    echo '  "Statement": ['
    echo '    {'
    echo '      "Effect": "Allow",'
    echo '      "Action": ["s3:PutObject", "s3:GetObject"],'
    echo '      "Resource": "arn:aws:s3:::'${S3_BUCKET}'/devices/'${DEVICE_ID}'/*"'
    echo '    },'
    echo '    {'
    echo '      "Effect": "Allow",'
    echo '      "Action": "s3:ListBucket",'
    echo '      "Resource": "arn:aws:s3:::'${S3_BUCKET}'"'
    echo '    }'
    echo '  ]'
    echo '}'
    exit 1
fi

# ========================================
# Step 7: サービスのセットアップ
# ========================================
echo -e "\n${YELLOW}🔧 Step 7: サービスのセットアップ${NC}\n"

cd ~/anpi-watch

# pir-watcher
echo "Setting up pir-watcher..."
sudo ln -sf ~/anpi-watch/pi/pir-watcher/pir-watcher.py      /usr/local/bin/pir-watcher.py
sudo ln -sf ~/anpi-watch/pi/pir-watcher/pir-watcher.service /etc/systemd/system/pir-watcher.service

# heartbeat
echo "Setting up heartbeat..."
sudo ln -sf ~/anpi-watch/pi/heartbeat/heartbeat.py      /usr/local/bin/heartbeat.py
sudo ln -sf ~/anpi-watch/pi/heartbeat/heartbeat.service /etc/systemd/system/heartbeat.service
sudo ln -sf ~/anpi-watch/pi/heartbeat/heartbeat.timer   /etc/systemd/system/heartbeat.timer

# anpi-update (自動デプロイ)
echo "Setting up anpi-update..."
sudo ln -sf ~/anpi-watch/pi/tools/anpi-update.sh      /usr/local/bin/anpi-update.sh
sudo ln -sf ~/anpi-watch/pi/tools/anpi-update.service /etc/systemd/system/anpi-update.service
sudo ln -sf ~/anpi-watch/pi/tools/anpi-update.timer   /etc/systemd/system/anpi-update.timer

# systemd reload
echo "Reloading systemd..."
sudo systemctl daemon-reload

# サービスの有効化
echo "Enabling services..."
sudo systemctl enable --now pir-watcher.service
sudo systemctl enable --now heartbeat.service
sudo systemctl enable --now heartbeat.timer
sudo systemctl enable --now anpi-update.service
sudo systemctl enable --now anpi-update.timer

echo -e "${GREEN}✓ サービスのセットアップ完了${NC}\n"

# デバイス同期デーモンのセットアップ（オプション）
if [ ! -f /etc/systemd/system/sync_device_config.timer ]; then
    echo -e "${YELLOW}デバイス設定同期デーモンをセットアップしますか？ (y/n):${NC}"
    read -p "> " SETUP_SYNC
    if [ "$SETUP_SYNC" = "y" ]; then
        echo "Setting up device sync daemon..."
        bash ~/anpi-watch/pi/sync_device_config/install.sh
    fi
fi

# ========================================
# Step 8: サービスの起動
# ========================================
echo -e "\n${YELLOW}🚀 Step 8: サービスの起動${NC}\n"

echo "Starting services..."
sudo systemctl start pir-watcher.service
sudo systemctl start heartbeat.service
sudo systemctl start heartbeat.timer
sudo systemctl start anpi-update.timer

# サービス状態の確認
echo -e "\n${BLUE}サービス状態:${NC}"
sudo systemctl is-active pir-watcher.service && echo -e "  pir-watcher:  ${GREEN}✓ active${NC}" || echo -e "  pir-watcher:  ${RED}✗ inactive${NC}"
sudo systemctl is-active heartbeat.service && echo -e "  heartbeat:    ${GREEN}✓ active${NC}" || echo -e "  heartbeat:    ${RED}✗ inactive${NC}"
sudo systemctl is-active heartbeat.timer && echo -e "  heartbeat (timer): ${GREEN}✓ active${NC}" || echo -e "  heartbeat (timer): ${RED}✗ inactive${NC}"
sudo systemctl is-active anpi-update.timer && echo -e "  anpi-update:  ${GREEN}✓ active${NC}" || echo -e "  anpi-update:  ${RED}✗ inactive${NC}"

# ========================================
# 完了
# ========================================
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ セットアップ完了！${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${BLUE}📋 次のステップ:${NC}"
echo ""
echo "1. サービスログの確認:"
echo "   ${YELLOW}sudo journalctl -u pir-watcher.service -f${NC}"
echo "   ${YELLOW}sudo journalctl -u heartbeat.service -f${NC}"
echo ""
echo "2. S3にデータが送信されているか確認:"
echo "   ${YELLOW}aws s3 ls s3://${S3_BUCKET}/devices/${DEVICE_ID}/${NC}"
echo ""
echo "3. システムを再起動（推奨）:"
echo "   ${YELLOW}sudo reboot${NC}"
echo ""

read -p "今すぐ再起動しますか？ (y/n): " REBOOT_NOW
if [ "$REBOOT_NOW" = "y" ]; then
    echo -e "${YELLOW}システムを再起動します...${NC}"
    sudo reboot
else
    echo -e "${YELLOW}手動で再起動してください: sudo reboot${NC}"
fi
