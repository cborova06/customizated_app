#!/usr/bin/env bash
# Translation Corruption Emergency Fix Script
# Run this script when "Bad translation" errors appear with HTML fragments
# Usage: bash translation_emergency_fix.sh

set -euo pipefail

BENCH_DIR="/home/frappe/frappe-bench"
SITE="helpdeskai.com"

echo "🚨 Translation Corruption Emergency Fix"
echo "========================================"
echo ""

# Step 1: Validate current files
echo "📋 Step 1: Validating translation files..."
bash "$BENCH_DIR/apps/brv_license_app/brv_license_app/scripts/validate_translations.sh"
VALIDATION_RESULT=$?

if [ $VALIDATION_RESULT -ne 0 ]; then
    echo ""
    echo "⚠️  CORRUPTED FILES DETECTED!"
    echo "Corrupted files will be removed automatically..."
    echo ""
    
    # Step 2: Remove corrupted files
    echo "🗑️  Step 2: Removing corrupted translation files..."
    REMOVED_COUNT=0
    while IFS= read -r -d '' csv_file; do
        first_line=$(head -1 "$csv_file" 2>/dev/null || echo "")
        if echo "$first_line" | grep -qE "<!DOCTYPE|<html|<head|<body"; then
            echo "   Removing: $csv_file"
            rm -v "$csv_file"
            REMOVED_COUNT=$((REMOVED_COUNT + 1))
        fi
    done < <(find "$BENCH_DIR/apps" -type f -name "*.csv" -path "*/translations/*" -print0 2>/dev/null)
    
    echo "   ✓ Removed $REMOVED_COUNT corrupted files"
else
    echo "   ✓ No corrupted files found"
fi

# Step 3: Clear all caches
echo ""
echo "🧹 Step 3: Clearing caches..."
cd "$BENCH_DIR"
bench --site "$SITE" clear-cache >/dev/null 2>&1
bench --site "$SITE" clear-website-cache >/dev/null 2>&1
echo "   ✓ Caches cleared"

# Step 4: Count error logs
echo ""
echo "📊 Step 4: Checking Error Log..."
ERROR_COUNT=$(bench --site "$SITE" mariadb -sN -e "SELECT COUNT(*) FROM \`tabError Log\` WHERE error LIKE '%Bad translation%';")
echo "   Found $ERROR_COUNT translation error logs"

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo ""
    read -p "   Delete these error logs? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "   Deleting error logs..."
        bench --site "$SITE" mariadb -e "SET SQL_SAFE_UPDATES = 0; DELETE FROM \`tabError Log\` WHERE error LIKE '%Bad translation%';" >/dev/null
        echo "   ✓ Error logs deleted"
    else
        echo "   Skipped deletion"
    fi
fi

# Step 5: Final validation
echo ""
echo "✅ Step 5: Final validation..."
bash "$BENCH_DIR/apps/brv_license_app/brv_license_app/scripts/validate_translations.sh" | tail -3

echo ""
echo "🎉 Translation corruption fix complete!"
echo ""
echo "Next steps:"
echo "  1. If any language translations are missing, re-download from Crowdin"
echo "  2. Always validate downloads: head -5 <file.csv>"
echo "  3. Monitor Error Log for new translation issues"
echo ""
echo "For details, see: $BENCH_DIR/TRANSLATION_CORRUPTION_FIX.md"
