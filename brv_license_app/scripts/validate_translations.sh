#!/usr/bin/env bash
# validate_translations.sh - Validate translation CSV files for corruption
# Usage: bash validate_translations.sh [apps_directory]
# Exit code: 0 if all valid, 1 if corruption found

set -euo pipefail

APPS_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)}"
CORRUPTED_COUNT=0
TOTAL_COUNT=0

echo "🔍 Scanning translation files in: $APPS_DIR"
echo ""

# Find all CSV files in translations directories
while IFS= read -r -d '' csv_file; do
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    
    # Check first line for HTML markers
    first_line=$(head -1 "$csv_file" 2>/dev/null || echo "")
    
    if echo "$first_line" | grep -qE "<!DOCTYPE|<html|<head|<body"; then
        echo "❌ CORRUPTED: $csv_file"
        echo "   First line: ${first_line:0:80}..."
        CORRUPTED_COUNT=$((CORRUPTED_COUNT + 1))
    fi
done < <(find "$APPS_DIR" -type f -name "*.csv" -path "*/translations/*" -print0 2>/dev/null)

echo ""
echo "📊 Summary:"
echo "   Total CSV files scanned: $TOTAL_COUNT"
echo "   Corrupted files found: $CORRUPTED_COUNT"

if [ $CORRUPTED_COUNT -gt 0 ]; then
    echo ""
    echo "⚠️  CORRUPTION DETECTED!"
    echo "   Run the following to remove corrupted files:"
    echo "   find $APPS_DIR -type f -name \"*.csv\" -path \"*/translations/*\" -exec sh -c 'head -1 \"\$1\" | grep -qE \"<!DOCTYPE|<html\" && rm -v \"\$1\"' _ {} \\;"
    exit 1
else
    echo "✅ All translation files are valid!"
    exit 0
fi
