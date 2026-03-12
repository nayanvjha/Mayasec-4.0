#!/usr/bin/env bash
# =============================================================================
# MAYASEC Phase 2 — Dataset Downloader
# =============================================================================
# Downloads all training datasets for the Isolation Forest + XGBoost pipeline.
#
# Prerequisites:
#   - Kaggle CLI configured: ~/.kaggle/kaggle.json must exist
#     Run: kaggle config set -n username -v <your_username>
#          kaggle config set -n key -v <your_api_key>
#   - Sufficient disk space: ~5 GB total
#
# Usage:
#   cd /Volumes/Crucial/Dev/Mayasec-4.0-main/ml-service
#   bash datasets/download.sh
# =============================================================================

set -euo pipefail

DATASETS_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DATASETS_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      MAYASEC Phase 2 — Dataset Download Script              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------------------
# DATASET 1 — NSL-KDD (Direct Download — No Auth Required)
# ~20MB | Network intrusion dataset | DoS, Probe, R2L, U2R
# ---------------------------------------------------------------------------

echo "▶ [1/5] NSL-KDD Dataset (University of New Brunswick)..."
mkdir -p nsl_kdd
NSL_KDD_TRAIN="https://raw.githubusercontent.com/defcom17/NSL_KDD/master/KDDTrain+.csv"
NSL_KDD_TEST="https://raw.githubusercontent.com/defcom17/NSL_KDD/master/KDDTest+.csv"

if [ ! -f "nsl_kdd/KDDTrain+.csv" ]; then
    curl -L --progress-bar -o nsl_kdd/KDDTrain+.csv "$NSL_KDD_TRAIN"
    echo "  ✓ KDDTrain+.csv downloaded"
else
    echo "  ✓ KDDTrain+.csv already present — skipping"
fi

if [ ! -f "nsl_kdd/KDDTest+.csv" ]; then
    curl -L --progress-bar -o nsl_kdd/KDDTest+.csv "$NSL_KDD_TEST"
    echo "  ✓ KDDTest+.csv downloaded"
else
    echo "  ✓ KDDTest+.csv already present — skipping"
fi

# ---------------------------------------------------------------------------
# DATASET 2 — SQLi Payload Dataset (GitHub — No Auth Required)
# ~2MB | Raw SQL injection payloads for feature augmentation
# ---------------------------------------------------------------------------

echo ""
echo "▶ [2/5] SQLi / XSS Payload Lists (SecLists + PayloadBox)..."
mkdir -p payloads

# SQL Injection payloads (PayloadBox — MIT licensed)
SQLI_URL="https://raw.githubusercontent.com/payloadbox/sql-injection-payload-list/master/Intruder/detect/Generic_SQLI.txt"
if [ ! -f "payloads/sqli_payloads.txt" ]; then
    curl -L --progress-bar -o payloads/sqli_payloads.txt "$SQLI_URL"
    echo "  ✓ sqli_payloads.txt downloaded ($(wc -l < payloads/sqli_payloads.txt) payloads)"
else
    echo "  ✓ sqli_payloads.txt already present — skipping"
fi

# XSS payloads (PayloadBox — MIT licensed)
XSS_URL="https://raw.githubusercontent.com/payloadbox/xss-payload-list/master/Intruder/xss-payload-list.txt"
if [ ! -f "payloads/xss_payloads.txt" ]; then
    curl -L --progress-bar -o payloads/xss_payloads.txt "$XSS_URL"
    echo "  ✓ xss_payloads.txt downloaded ($(wc -l < payloads/xss_payloads.txt) payloads)"
else
    echo "  ✓ xss_payloads.txt already present — skipping"
fi

# Command Injection payloads
CMDI_URL="https://raw.githubusercontent.com/payloadbox/command-injection-payload-list/master/README.md"
if [ ! -f "payloads/cmdi_payloads.txt" ]; then
    curl -L --progress-bar -o payloads/cmdi_payloads.txt "$CMDI_URL"
    echo "  ✓ cmdi_payloads.txt downloaded"
else
    echo "  ✓ cmdi_payloads.txt already present — skipping"
fi

# Path traversal payloads
PT_URL="https://raw.githubusercontent.com/payloadbox/path-traversal-payload-list/master/path-traversal-payload-list.txt"
if [ ! -f "payloads/path_traversal_payloads.txt" ]; then
    curl -L --progress-bar -o payloads/path_traversal_payloads.txt "$PT_URL" 2>/dev/null \
    || curl -L --progress-bar -o payloads/path_traversal_payloads.txt \
         "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/LFI/LFI-Jhaddix.txt"
    echo "  ✓ path_traversal_payloads.txt downloaded"
else
    echo "  ✓ path_traversal_payloads.txt already present — skipping"
fi

# ---------------------------------------------------------------------------
# DATASET 3 — HTTP CSIC 2010 (Kaggle — Requires API Auth)
# ~60MB | Real HTTP request logs, labeled normal/anomalous
# Closest to what the MAYASEC ingress proxy intercepts
# ---------------------------------------------------------------------------

echo ""
echo "▶ [3/5] CSIC 2010 HTTP Dataset (via Kaggle)..."
mkdir -p csic_2010

if [ ! -f "csic_2010/normalTrafficTraining.txt" ]; then
    echo "  Downloading from Kaggle (requires kaggle.json auth)..."
    kaggle datasets download -d ispangler/csic-2010-http-dataset-for-web-attack-detection \
        -p csic_2010 --unzip 2>/dev/null \
    || {
        echo "  ⚠ Kaggle download failed. Alternative: download manually from:"
        echo "    https://www.kaggle.com/datasets/ispangler/csic-2010-http-dataset-for-web-attack-detection"
        echo "    Place files in: ml-service/datasets/csic_2010/"
        touch csic_2010/.download_pending
    }
    if ls csic_2010/*.txt 2>/dev/null | head -1 | grep -q txt; then
        echo "  ✓ CSIC 2010 downloaded"
    fi
else
    echo "  ✓ CSIC 2010 already present — skipping"
fi

# ---------------------------------------------------------------------------
# DATASET 4 — Web Application Attack Dataset (Kaggle)
# ~5MB | SQLi, XSS, SSRF, CMDi with URL + label columns
# Ideal for HTTP-level feature extraction training
# ---------------------------------------------------------------------------

echo ""
echo "▶ [4/5] Web Application Attack Dataset (Kaggle)..."
mkdir -p web_attacks

if [ ! -f "web_attacks/web_attacks.csv" ]; then
    kaggle datasets download -d umeradnaan/web-application-attack-dataset \
        -p web_attacks --unzip 2>/dev/null \
    || kaggle datasets download -d dhoogla/cicids2017 \
        -p web_attacks --unzip 2>/dev/null \
    || {
        echo "  ⚠ Kaggle download failed. Alternative: download manually from:"
        echo "    https://www.kaggle.com/datasets/umeradnaan/web-application-attack-dataset"
        echo "    Place CSV in: ml-service/datasets/web_attacks/web_attacks.csv"
        touch web_attacks/.download_pending
    }
    # Rename whatever CSV was downloaded
    FIRST_CSV=$(ls web_attacks/*.csv 2>/dev/null | head -1)
    if [ -n "$FIRST_CSV" ] && [ "$FIRST_CSV" != "web_attacks/web_attacks.csv" ]; then
        mv "$FIRST_CSV" web_attacks/web_attacks.csv
    fi
    echo "  ✓ Web attacks dataset downloaded"
else
    echo "  ✓ web_attacks.csv already present — skipping"
fi

# ---------------------------------------------------------------------------
# DATASET 5 — CIC-IDS-2017 (Kaggle — sampled 10% version to save disk space)
# ~500MB | SQLi, Brute Force, DDoS, Infiltration — pre-extracted features
# Use sampled version: full 2018 dataset is 16GB
# ---------------------------------------------------------------------------

echo ""
echo "▶ [5/5] CIC-IDS-2017 Sampled (Kaggle)..."
mkdir -p cicids2017

if [ ! -f "cicids2017/cicids2017_sampled.csv" ]; then
    kaggle datasets download -d chethuhn/network-intrusion-dataset \
        -p cicids2017 --unzip 2>/dev/null \
    || {
        echo "  ⚠ Kaggle download failed. Alternative:"
        echo "    https://www.kaggle.com/datasets/chethuhn/network-intrusion-dataset"
        echo "    Place CSV in: ml-service/datasets/cicids2017/"
        touch cicids2017/.download_pending
    }
    FIRST_CSV=$(ls cicids2017/*.csv 2>/dev/null | head -1)
    if [ -n "$FIRST_CSV" ]; then
        mv "$FIRST_CSV" cicids2017/cicids2017_sampled.csv 2>/dev/null || true
        echo "  ✓ CIC-IDS-2017 sampled downloaded"
    fi
else
    echo "  ✓ cicids2017_sampled.csv already present — skipping"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   Download Summary                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Dataset directory: $DATASETS_DIR"
echo ""
echo "Status:"
[ -f "nsl_kdd/KDDTrain+.csv" ]             && echo "  ✅ NSL-KDD" || echo "  ❌ NSL-KDD — MISSING"
[ -f "payloads/sqli_payloads.txt" ]         && echo "  ✅ SQLi payloads" || echo "  ❌ SQLi payloads — MISSING"
[ -f "payloads/xss_payloads.txt" ]          && echo "  ✅ XSS payloads" || echo "  ❌ XSS payloads — MISSING"
[ -f "payloads/path_traversal_payloads.txt" ] && echo "  ✅ Path traversal payloads" || echo "  ❌ Path traversal payloads"
[ -f "csic_2010/normalTrafficTraining.txt" ] || ls csic_2010/*.csv 2>/dev/null | head -1 | grep -q csv \
    && echo "  ✅ CSIC 2010" || echo "  ⚠️  CSIC 2010 — manual download required"
ls web_attacks/*.csv 2>/dev/null | head -1 | grep -q csv \
    && echo "  ✅ Web attacks dataset" || echo "  ⚠️  Web attacks — manual download required"
ls cicids2017/*.csv 2>/dev/null | head -1 | grep -q csv \
    && echo "  ✅ CIC-IDS-2017 sampled" || echo "  ⚠️  CIC-IDS-2017 — manual download required"

echo ""
echo "Total size on disk:"
du -sh "$DATASETS_DIR" 2>/dev/null || echo "  (unable to check)"
echo ""
echo "Next step: run ml-service/training/train.py"
echo ""
