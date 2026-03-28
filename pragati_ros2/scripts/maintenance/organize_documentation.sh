#!/bin/bash

# Documentation Organization Script
# Moves scattered documentation files to proper docs/ structure

echo "🗂️  PRAGATI ROS2 - Documentation Organization"
echo "=============================================="

# Create timestamp for backup
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="docs_reorganization_backup_${TIMESTAMP}"

# Create backup directory
mkdir -p "$BACKUP_DIR"
echo "📁 Created backup directory: $BACKUP_DIR"

# Define documentation files to move
declare -A DOC_FILES=(
    # Main directory docs -> docs/reports/
    ["ACTUAL_DEVELOPMENT_ROADMAP.md"]="docs/reports/"
    ["CURRENT_SYSTEM_STATUS.md"]="docs/reports/"
    ["DOCUMENTATION_UPDATE_VALIDATION.md"]="docs/validation/"
    ["IMMEDIATE_ACTION_ITEMS.md"]="docs/reports/"
    ["ISSUE_RESOLUTION_REPORT.md"]="docs/reports/"
    
    # CHANGELOG should stay in root but create link in docs
    # README.md should stay in root but create organized version in docs
)

# Create necessary subdirectories in docs/
echo ""
echo "📂 Creating documentation subdirectories..."
mkdir -p docs/reports
mkdir -p docs/validation
mkdir -p docs/guides
mkdir -p docs/reference

# Function to move and organize files
organize_file() {
    local file="$1"
    local dest_dir="$2"
    
    if [[ -f "$file" ]]; then
        echo "  📄 Moving $file -> $dest_dir"
        
        # Create backup
        cp "$file" "$BACKUP_DIR/"
        
        # Move to destination
        mv "$file" "$dest_dir"
        
        # Update any references in the moved file
        if [[ -f "$dest_dir/$(basename "$file")" ]]; then
            # Fix relative paths that might be broken by moving
            sed -i 's|\.\/|\.\.\/|g' "$dest_dir/$(basename "$file")" 2>/dev/null
        fi
    else
        echo "  ⚠️  File not found: $file"
    fi
}

echo ""
echo "📋 Organizing documentation files..."

# Move files to appropriate locations
for file in "${!DOC_FILES[@]}"; do
    organize_file "$file" "${DOC_FILES[$file]}"
done

# Handle special cases
echo ""
echo "🔗 Creating documentation index and references..."

# Create main docs README that references everything
cat > docs/README.md << 'EOF'
# PRAGATI ROS2 Documentation

This directory contains all project documentation organized by category.

## 📁 Directory Structure

- **`reports/`** - System status reports, development roadmaps, and action items
- **`validation/`** - Validation procedures, test reports, and verification documents  
- **`guides/`** - User guides, setup instructions, and how-to documents
- **`reference/`** - API documentation, configuration references, and technical specs
- **`development/`** - Development notes, architecture docs, and design decisions
- **`deployment/`** - Deployment guides, installation procedures, and production docs
- **`archive/`** - Historical documentation and deprecated files

## 📋 Quick Reference

### System Status & Reports
- [Current System Status](reports/CURRENT_SYSTEM_STATUS.md)
- [Development Roadmap](reports/ACTUAL_DEVELOPMENT_ROADMAP.md)  
- [Immediate Action Items](reports/IMMEDIATE_ACTION_ITEMS.md)
- [Issue Resolution Report](reports/ISSUE_RESOLUTION_REPORT.md)

### Validation & Testing
- [Documentation Update Validation](validation/DOCUMENTATION_UPDATE_VALIDATION.md)
- [Project Master Guide](PROJECT_MASTER_GUIDE.md)
- [Verification Traceability Matrix](VERIFICATION_TRACEABILITY_MATRIX.md)

### Main Project Files
- [Main README](../README.md) - Primary project documentation
- [CHANGELOG](../CHANGELOG.md) - Version history and changes

## 🔍 Finding Documentation

Use the organized structure above, or search by topic:
- **Setup & Installation**: See `guides/` and `deployment/`
- **API & Configuration**: See `reference/`  
- **Testing & Validation**: See `validation/`
- **System Status**: See `reports/`
EOF

# Create symbolic links in root for important docs (if needed)
echo ""
echo "🔗 Creating convenience links..."

# Create docs reference in main README if not exists
if ! grep -q "docs/" README.md 2>/dev/null; then
    echo "" >> README.md
    echo "## 📚 Documentation" >> README.md
    echo "" >> README.md
    echo "Complete documentation is organized in the [\`docs/\`](docs/) directory:" >> README.md
    echo "" >> README.md
    echo "- [Documentation Index](docs/README.md)" >> README.md
    echo "- [System Status Reports](docs/reports/)" >> README.md
    echo "- [Validation Documents](docs/validation/)" >> README.md
    echo "- [User Guides](docs/guides/)" >> README.md
    echo "" >> README.md
fi

# Generate organization report
echo ""
echo "📊 Generating organization report..."

cat > "docs_organization_report_${TIMESTAMP}.md" << EOF
# Documentation Organization Report
Generated: $(date)

## Files Moved
$(for file in "${!DOC_FILES[@]}"; do
    if [[ -f "${DOC_FILES[$file]}/$(basename "$file")" ]]; then
        echo "✅ $file → ${DOC_FILES[$file]}"
    else
        echo "❌ $file (failed to move)"
    fi
done)

## Directory Structure After Organization
\`\`\`
docs/
$(tree docs/ 2>/dev/null || find docs/ -type d | sed 's|[^/]*/|  |g')
\`\`\`

## Files Preserved in Root
- README.md (main project documentation)
- CHANGELOG.md (version history)
- pyproject.toml (Python project configuration)

## Backup Location
All original files backed up to: $BACKUP_DIR/

## Next Steps
1. Update any scripts/tools that reference moved documentation files
2. Verify all internal documentation links still work
3. Update CI/CD pipelines if they reference specific doc paths
4. Consider adding automated doc organization to future workflows
EOF

echo ""
echo "✅ DOCUMENTATION ORGANIZATION COMPLETE!"
echo "======================================"
echo "📁 Backup created: $BACKUP_DIR/"
echo "📊 Report generated: docs_organization_report_${TIMESTAMP}.md"
echo "📚 New docs structure: docs/README.md"
echo ""
echo "🔍 Verification:"
echo "  - Check docs/README.md for new organization"
echo "  - Verify moved files are in correct locations"  
echo "  - Update any external references to moved files"
echo ""