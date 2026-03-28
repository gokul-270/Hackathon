#!/usr/bin/env python3
"""
Audit steps 7-10: Link analysis, duplicates, and recommendations
"""
import os, re, csv, pathlib
from collections import defaultdict

docs = os.environ["DOCS"]
reports = os.environ["REPORTS"]
cutoff = os.environ["CUTOFF"]
archive_dir = os.path.join(docs, "archive")

print("Step 7: Building link index...")
link_re = re.compile(r'\[([^\]]+)\]\(((?!https?://|mailto:|#|/)[^)]+)\)')
heading_re = re.compile(r'^\s{0,3}#+\s+(.*)')

def anchors_for(path):
    anchors = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = heading_re.match(line)
                if m:
                    t = m.group(1).strip().lower()
                    t = re.sub(r'[^\w\s-]', '', t)
                    t = re.sub(r'\s+', '-', t)
                    anchors.add(t)
    except Exception:
        pass
    return anchors

all_md = [str(p) for p in pathlib.Path(docs).rglob("*.md")]
exists_set = set(all_md)

edges = []
broken = []
to_archive = []

for p in all_md:
    try:
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, start=1):
                for m in link_re.finditer(line):
                    dest = m.group(2).split('#')[0]
                    dest_path = os.path.normpath(os.path.join(os.path.dirname(p), dest))
                    edges.append((p, dest_path))
                    
                    if dest_path not in exists_set:
                        broken.append([p, i, m.group(0), dest_path])
                    if dest_path.startswith(archive_dir):
                        to_archive.append([p, i, dest_path])
    except Exception:
        pass

with open(os.path.join(reports, "internal_links.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["from", "to"])
    w.writerows(edges)

with open(os.path.join(reports, "broken_links.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["from_file", "line", "link_snippet", "resolved_target"])
    w.writerows(broken)

with open(os.path.join(reports, "links_to_archive.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["from_file", "line", "target_in_archive"])
    w.writerows(to_archive)

with open(os.path.join(reports, "circular_references.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["cycle_paths"])

print(f"  {len(edges)} links, {len(broken)} broken, {len(to_archive)} to archive")

print("Step 8: Detecting duplicates...")
def norm(name):
    base = os.path.splitext(os.path.basename(name))[0].lower()
    base = re.sub(r'(19|20)\d{2}(-\d{2}(-\d{2})?)?', '', base)
    base = re.sub(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{4}', '', base)
    base = re.sub(r'\b(v?\d+|v\d+\.\d+)\b', '', base)
    base = re.sub(r'\b(draft|old|copy|backup|temp)\b', '', base)
    tokens = re.split(r'[^a-z0-9]+', base)
    tokens = [t for t in tokens if t and t not in {'the','and','of','for','to','in','docs','doc'}]
    return "-".join(sorted(tokens)) or base

clusters = defaultdict(list)
for p in all_md:
    k = norm(p)
    clusters[k].append(p)

dups = {k: v for k, v in clusters.items() if len(v) > 1}

with open(os.path.join(reports, "duplicates_by_name.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["normalized_key", "paths"])
    for k, vs in sorted(dups.items(), key=lambda x: (-len(x[1]), x[0])):
        w.writerow([k, " | ".join(vs)])

print(f"  {len(dups)} duplicate clusters found")

print("Step 9: Finding canonical claims...")
os.system(f'grep -RIn -E "(source of truth|canonical|authoritative)" "{docs}" > "{reports}/canonical_claims.txt" 2>/dev/null || touch "{reports}/canonical_claims.txt"')

claims = set()
try:
    with open(os.path.join(reports, "canonical_claims.txt")) as f:
        for line in f:
            if ":" in line:
                claims.add(line.split(":", 1)[0])
except:
    pass

conflicts = {}
for k, files in dups.items():
    if any(p in claims for p in files):
        conflicts[k] = files

with open(os.path.join(reports, "potential_conflicts.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["normalized_key", "files"])
    for k, v in conflicts.items():
        w.writerow([k, " | ".join(v)])

print(f"  {len(conflicts)} potential conflicts")

print("Step 10: Generating recommendations...")
def load_set(path):
    s = set()
    if not os.path.exists(path):
        return s
    with open(path) as f:
        for line in f:
            if ":" in line:
                s.add(line.split(":", 1)[0])
    return s

redirects = load_set(os.path.join(reports, "redirect_notices.txt"))
statusflag = load_set(os.path.join(reports, "status_markers.txt"))

stales = {}
with open(os.path.join(reports, "last_updated_all.csv")) as f:
    r = csv.DictReader(f)
    for row in r:
        stales[row["path"]] = row["staleness"]

dups_keys = {}
for k, paths in dups.items():
    for p in paths:
        dups_keys[p] = k

links_to_archive_set = set(row[0] for row in to_archive)
broken_by_file = set(row[0] for row in broken)

rows = []
for p in all_md:
    rec = "KEEP"
    reasons = []
    
    if p in redirects:
        rec = "ARCHIVE"
        reasons.append("redirect_notice")
    if p in statusflag:
        rec = "ARCHIVE"
        reasons.append("status_marker")
    
    st = stales.get(p, "")
    if st == "STALE":
        if rec == "KEEP":
            rec = "UPDATE"
        reasons.append(f"stale_before_{cutoff}")
    
    if p in dups_keys:
        if rec == "KEEP":
            rec = "CONSOLIDATE"
        reasons.append(f"duplicate_topic:{dups_keys[p]}")
    
    if p in broken_by_file:
        if rec == "KEEP":
            rec = "UPDATE"
        reasons.append("has_broken_links")
    
    if p in links_to_archive_set:
        reasons.append("references_archived")
    
    rows.append([p, rec, ";".join(reasons)])

with open(os.path.join(reports, "audit_recommendations.csv"), "w", newline='') as out:
    w = csv.writer(out)
    w.writerow(["path", "recommendation", "reasons"])
    w.writerows(rows)

cats = {"KEEP": 0, "ARCHIVE": 0, "CONSOLIDATE": 0, "DELETE": 0, "UPDATE": 0}
for _, rec, _ in rows:
    cats[rec] = cats.get(rec, 0) + 1

with open(os.path.join(reports, "AUDIT_SUMMARY.md"), "w") as out:
    out.write("# Audit Summary (auto-generated)\n\n")
    for k in ["KEEP", "ARCHIVE", "CONSOLIDATE", "UPDATE", "DELETE"]:
        out.write(f"- {k}: {cats.get(k, 0)}\n")
    out.write("\nSee audit_recommendations.csv for details.\n")

print("  Recommendations:")
for k in ["KEEP", "ARCHIVE", "CONSOLIDATE", "UPDATE", "DELETE"]:
    if cats.get(k, 0) > 0:
        print(f"    {k}: {cats[k]}")

print("\nAudit complete!")
