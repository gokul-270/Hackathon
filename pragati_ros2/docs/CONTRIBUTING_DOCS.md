# Contributing to Documentation

**Last Updated:** 2025-10-21  
**Purpose:** Guidelines for maintaining clean, organized documentation

## Quick Rules

1. **Update canonical docs only** - Don't create parallel versions
2. **Add date headers** - Every doc should have `**Last Updated:** YYYY-MM-DD`
3. **Link to canonical sources** - Use the definitive docs listed below
4. **Archive properly** - Add redirect notes when replacing docs

## Canonical Documents (Source of Truth)

These are the definitive documents. Update these, not copies:

- `PRODUCTION_READINESS_GAP.md` - Production status and validation plan
- `TODO_MASTER_CONSOLIDATED.md` - Active TODO list
- `CONSOLIDATED_ROADMAP.md` - Actionable work plan
- `STATUS_REALITY_MATRIX.md` - Reality check document
- `INDEX.md` - Central navigation hub
- `START_HERE.md` - Onboarding guide

## When Creating New Documentation

### ✅ DO:
- Check if a doc already exists for your topic
- Update the existing doc if it covers your topic
- Add `**Last Updated:** YYYY-MM-DD` at the top
- Link to related canonical docs
- Keep it concise and focused

### ❌ DON'T:
- Create duplicate docs (e.g., "ROADMAP_v2.md" when CONSOLIDATED_ROADMAP.md exists)
- Use temporary names (e.g., "DRAFT_", "NEW_", "TEMP_")
- Forget to update the date header
- Leave broken links

## When Updating Existing Documentation

1. **Check the date** - Is it current?
2. **Update the header** - Change `**Last Updated:**` to today
3. **Fix broken links** - Check references still work
4. **Preserve history** - Don't delete valuable info, archive it instead

## When Superseding a Document

If you're replacing an old doc with a new one:

1. **Add a redirect notice** to the old doc:
   ```markdown
   > **Note:** This document is superseded. See [NEW_DOC.md](./NEW_DOC.md) for current information.
   ```

2. **Move to archive** if it's truly outdated:
   ```bash
   mv old_doc.md docs/archive/YYYY-MM-DD/
   ```

3. **Update archive/INDEX.md** with reason and replacement link

4. **Update links** - Find and replace references to the old doc

## Checking Documentation Health

### Monthly: Quick Check
```bash
# Find docs without dates
grep -rL "Last Updated" docs --include="*.md" --exclude-dir=archive

# Find broken links
find docs -name "*.md" -exec grep -l "\](.*/" {} \;
```

### Quarterly: Full Audit
Manually review:
- Check `STATUS_REALITY_MATRIX.md` is up to date
- Verify links in `INDEX.md` work
- Archive stale content to `archive/YYYY-MM/`

## Link Best Practices

- Use **relative links**: `[Guide](./guides/GUIDE.md)` not absolute paths
- For archived docs: Link to the replacement, not the archive
- Check links after moving/renaming files

## Archive Organization

```
docs/
├── archive/
│   ├── INDEX.md              # Archive index with reasons
│   ├── 2025-10/              # October 2025 consolidation
│   ├── 2025-10-15/           # Pre-consolidation snapshots
│   └── YYYY-MM-DD/           # Date-stamped archives
```

**Archive naming**: Use `YYYY-MM-DD` for clarity (e.g., `2025-10-21/`)

## Common Mistakes to Avoid

1. **Version suffixes** - Don't use `_v2`, `_final`, `_updated`
   - Instead: Update the canonical doc and archive the old version

2. **Status in filenames** - Don't use `DRAFT_`, `WIP_`, `OLD_`
   - Instead: Use status headers inside the doc

3. **Duplicate topics** - Don't create `MOTOR_GUIDE.md` if `guides/MOTOR_TUNING_GUIDE.md` exists
   - Instead: Update the existing guide

4. **Temporary docs** - Don't leave `TEMP_NOTES.md` lying around
   - Instead: Integrate into a canonical doc or delete

## When in Doubt

1. Check `docs/INDEX.md` for the canonical location
2. Search for existing docs: `find docs -name "*keyword*.md"`
3. Ask the team before creating major new docs

### Manual Checks
```bash
# Find recent docs
find docs -name "*.md" -mtime -7 -not -path "*/archive/*"

# Count active docs
find docs -name "*.md" -not -path "*/archive/*" | wc -l

# Search for term
grep -r "search term" docs --include="*.md" --exclude-dir=archive
```

## Questions?

- Check the index: `docs/INDEX.md`
- See what changed: `git log --oneline docs/`

---

**Remember:** Clean docs save everyone time. Update canonical sources, archive old versions, and keep links working!
