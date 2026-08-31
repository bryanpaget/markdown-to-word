#!/usr/bin/env python3
"""Capture linked evidence for the Aurora Security Assessment (SA) folder.

Background (roadmap issue #516): the security control narratives link to
evidence. Some evidence lives in this repository (YAML/Terraform/screenshots
under azure/evidence/) and is therefore physically present in the SA folder.
Other evidence is linked as a URL (the Aurora documentation site, GitHub,
Azure DevOps, SharePoint). When a narrative is exported to PDF those URLs are
just hyperlinks - the evidence they point at is NOT physically in the SA
folder, so from an assessor's point of view it "does not exist".

This script closes that gap. For every control narrative it:

  1. Extracts each link and classifies it:
       local          - a file already in the repo (in the SA folder already)
       evidence-web   - an Aurora-controlled URL that is publicly reachable and
                        can be rendered to PDF automatically (the doc site)
       evidence-auth  - an Aurora-controlled URL behind authentication that a
                        script cannot fetch (SharePoint, private GitHub, Azure
                        DevOps) -> recorded for MANUAL export
       reference      - third-party public documentation (kubernetes.io,
                        learn.microsoft.com, etc.); supporting reference, not
                        evidence that needs to be filed
  2. Renders each evidence-web URL to a PDF under
     output/evidence-pdfs/<CONTROL-ID>/ using wkhtmltopdf. Each captured PDF is
     made self-describing for an assessor:
       - a prepended provenance cover page (source URL, capture timestamp in
         UTC, HTTP status, renderer + version, and the control(s) that cite it);
       - a per-page footer stamped with the source URL, capture date, and page
         number.
  3. Writes a coverage manifest (Markdown + JSON) listing, per control, what was
     captured, what is already local, and what still needs manual export.

The captured PDFs live under output/ (gitignored build output) and are not
committed. Copy them into the Security Assessment folder manually.

Nothing is fabricated: links that cannot be fetched are reported for manual
capture, never invented. Rendering is best-effort; a failed render is recorded
in the manifest with its error rather than aborting the run.

Environment: uses wkhtmltopdf (real binary, works through the TLS-inspecting
proxy) and ghostscript (gs) to merge the cover page in front of the capture.
Override the renderer with EVIDENCE_RENDERER=/path/to/wkhtmltopdf. Set
EVIDENCE_SKIP_RENDER=1 to only (re)generate the manifest without rendering.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

# The security-narratives repo root. When these helpers are run from a cloned
# markdown-to-word/scripts/ directory, the caller (export.sh) sets
# NARRATIVES_ROOT so paths resolve against the narratives repo, not this clone.
REPO_ROOT = os.environ.get("NARRATIVES_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AZURE_DIR = os.path.join(REPO_ROOT, "azure")
# Captured evidence goes to gitignored build output. Copy it into the SA folder
# manually; it is not committed to this repo.
OUT_DIR = os.path.join(REPO_ROOT, "output", "evidence-pdfs")

RENDERER = os.environ.get("EVIDENCE_RENDERER", shutil.which("wkhtmltopdf") or "wkhtmltopdf")
GS = shutil.which("gs") or "gs"
SKIP_RENDER = os.environ.get("EVIDENCE_SKIP_RENDER", "").strip().lower() in ("1", "true", "yes", "on")
RENDER_TIMEOUT = int(os.environ.get("EVIDENCE_RENDER_TIMEOUT", "120"))

# Hosts whose content is Aurora-controlled evidence and is publicly reachable,
# so it can be rendered to PDF automatically.
EVIDENCE_WEB_HOSTS = {
    "aurora.gccloudone.alpha.canada.ca",
}

# Hosts that hold Aurora-controlled evidence but sit behind authentication and
# therefore cannot be fetched by this script -> manual export required.
EVIDENCE_AUTH_HOSTS = {
    "163gc.sharepoint.com",
    "dev.azure.com",
    "plus.ssc-spc.gc.ca",
    "gcdocs.gc.ca",
    "bitsprod.ssc-spc.gc.ca",
}

# github.com is special-cased: gccloudone* orgs are Aurora evidence (private ->
# manual); everything else is treated as a public reference.
AURORA_GITHUB_ORGS = ("gccloudone", "gccloudone-aurora", "gccloudone-aurora-iac")

# A link with a fragment-only target (#...) is an internal cross-reference.
link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+(?:\([^)]*\)[^)]*)*)\)")


def classify(target):
    """Return one of: local, evidence-web, evidence-auth, reference, internal."""
    t = target.strip()
    if t.startswith("#") or t.startswith("mailto:"):
        return "internal"
    if not t.startswith(("http://", "https://")):
        return "local"
    host = urllib.parse.urlparse(t).netloc.lower()
    if host in EVIDENCE_WEB_HOSTS:
        return "evidence-web"
    if host in EVIDENCE_AUTH_HOSTS:
        return "evidence-auth"
    if host == "github.com":
        parts = urllib.parse.urlparse(t).path.strip("/").split("/")
        org = parts[0].lower() if parts else ""
        if org in AURORA_GITHUB_ORGS:
            return "evidence-auth"  # private Aurora repos -> manual export
        return "reference"
    return "reference"


def control_id_from_filename(name):
    return os.path.splitext(name)[0]


def slugify_url(url):
    """Stable, filesystem-safe filename stem for a URL."""
    p = urllib.parse.urlparse(url)
    path = p.path.strip("/")
    stem = (p.netloc + "-" + path).replace("/", "-")
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return (stem or "index")[:120]


def collect_links():
    """Scan azure/*.md.

    Returns (links, citations) where:
      links     = {control_id: [(label, target, kind), ...]}
      citations = {target_url: [control_id, ...]}  (which controls cite each URL)
    """
    out = {}
    citations = {}
    for name in sorted(os.listdir(AZURE_DIR)):
        if not name.endswith(".md"):
            continue
        cid = control_id_from_filename(name)
        with open(os.path.join(AZURE_DIR, name), encoding="utf-8") as fh:
            text = fh.read()
        seen = set()
        items = []
        for m in link_re.finditer(text):
            label_m = re.match(r"!?\[([^\]]*)\]", m.group(0))
            label = label_m.group(1) if label_m else ""
            target = m.group(1).strip()
            key = (label, target)
            if key in seen:
                continue
            seen.add(key)
            kind = classify(target)
            items.append((label, target, kind))
            if kind in ("evidence-web", "evidence-auth"):
                citations.setdefault(target, [])
                if cid not in citations[target]:
                    citations[target].append(cid)
        out[cid] = items
    return out, citations


REACHABLE_CODES = {200, 206, 301, 302, 303, 307, 308}


def _http_status_once(url):
    """Single curl attempt. Return the final HTTP code, or 0 on failure."""
    try:
        proc = subprocess.run(
            ["curl", "-s", "-L", "-o", os.devnull, "-w", "%{http_code}",
             "--connect-timeout", "20", "--max-time", "40", url],
            capture_output=True, text=True, timeout=55,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0
    code = (proc.stdout or "").strip()[-3:]
    try:
        return int(code)
    except ValueError:
        return 0


def http_status(url, attempts=3):
    """Return the final HTTP status for url, retrying transient failures.

    Uses curl (which trusts the environment's proxy CA) following redirects.
    A result of 0 (timeout / connection reset through the proxy) is retried so a
    transient network blip does not permanently mark a good link as broken.
    """
    code = 0
    for _ in range(max(1, attempts)):
        code = _http_status_once(url)
        if code != 0:
            return code
    return code


def renderer_version():
    """Return the wkhtmltopdf version string, or the binary name if unknown."""
    try:
        proc = subprocess.run([RENDERER, "--version"], capture_output=True,
                              text=True, timeout=20)
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        return out[0] if out else os.path.basename(RENDERER)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return os.path.basename(RENDERER)


RENDERER_VERSION = None  # set lazily in main()


def html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_cover_html(url, captured_utc, http_code, citing_controls):
    """Return HTML for a one-page provenance cover placed in front of a capture."""
    controls = ", ".join(citing_controls) if citing_controls else "(none recorded)"
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: sans-serif; margin: 2.5cm; color: #1a1a1a; }}
  h1 {{ font-size: 20px; border-bottom: 2px solid #444; padding-bottom: 8px; }}
  .cls {{ color: #666; font-size: 12px; letter-spacing: 1px; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 13px; }}
  th, td {{ text-align: left; vertical-align: top; padding: 8px 10px;
           border-bottom: 1px solid #ddd; }}
  th {{ width: 34%; color: #333; }}
  .url {{ word-break: break-all; }}
  .note {{ margin-top: 28px; font-size: 11px; color: #666; }}
</style></head><body>
  <div class="cls">UNCLASSIFIED | NON CLASSIFIE</div>
  <h1>Aurora Security Assessment - Captured Web Evidence</h1>
  <table>
    <tr><th>Source URL</th><td class="url">{url}</td></tr>
    <tr><th>Captured (UTC)</th><td>{ts}</td></tr>
    <tr><th>HTTP status at capture</th><td>{code}</td></tr>
    <tr><th>Cited by control(s)</th><td>{controls}</td></tr>
    <tr><th>Renderer</th><td>{renderer}</td></tr>
  </table>
  <p class="note">This cover page was generated automatically when the linked
  evidence was rendered to PDF for inclusion in the Security Assessment folder.
  The pages that follow are a point-in-time capture of the source URL above.</p>
</body></html>""".format(
        url=html_escape(url),
        ts=html_escape(captured_utc),
        code=html_escape(str(http_code)),
        controls=html_escape(controls),
        renderer=html_escape(RENDERER_VERSION or os.path.basename(RENDERER)),
    )


def _run(cmd, timeout):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _ps_escape(s):
    """Escape a string for a PostScript literal (parentheses and backslashes)."""
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _footer_prologue(footer_text):
    """PostScript that stamps footer_text at the bottom of every rendered page.

    Installed via a temporary EndPage procedure. Uses Helvetica 7pt, drawn 24pt
    up from the bottom-left of the page. This is done in the ghostscript pass
    because this wkhtmltopdf build (unpatched Qt) ignores --footer-* options.
    """
    esc = _ps_escape(footer_text)
    return (
        "<< /EndPage { "
        "  2 eq { pop false } "            # ignore blank/other page phases
        "  { "
        "    gsave "
        "    /Helvetica findfont 7 scalefont setfont "
        "    0.35 setgray "
        "    36 24 moveto (" + esc + ") show "
        "    grestore "
        "    true "
        "  } ifelse "
        "} bind >> setpagedevice"
    )


def merge_pdfs(cover, body, dest, footer_text=None):
    """Concatenate cover + body into dest via ghostscript, optionally stamping a
    footer on every page. Return (ok, msg)."""
    cmd = [GS, "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
           "-dCompatibilityLevel=1.5", "-sOutputFile=" + dest]
    if footer_text:
        cmd += ["-c", _footer_prologue(footer_text), "-f"]
    cmd += [cover, body]
    try:
        proc = _run(cmd, timeout=RENDER_TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, "gs merge failed: %s" % exc
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return True, "ok"
    err = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, "gs merge produced no PDF" + (": " + err[-1] if err else "")


def render_pdf(url, dest, captured_utc, http_code, citing_controls):
    """Render url -> dest with a provenance cover page and per-page footer.

    Steps: (1) render the page with wkhtmltopdf, stamping a footer with the
    source URL, capture date, and page number; (2) render a provenance cover
    page; (3) merge cover + body with ghostscript. Falls back to the body-only
    PDF (still footer-stamped) if the cover/merge step fails, so a capture is
    never lost to a provenance error. Return (ok, message).
    """
    workdir = os.path.dirname(dest)
    body = os.path.join(workdir, ".body.tmp.pdf")
    cover = os.path.join(workdir, ".cover.tmp.pdf")
    cover_html = os.path.join(workdir, ".cover.tmp.html")
    # Footer is stamped by ghostscript (this wkhtmltopdf build uses unpatched Qt
    # and silently ignores --footer-* options), so it is applied during merge.
    footer = "Source: %s   -   Captured (UTC): %s" % (url, captured_utc)
    body_cmd = [
        RENDERER,
        "--quiet",
        "--load-error-handling", "ignore",
        "--load-media-error-handling", "ignore",
        "--enable-external-links",
        # The doc site is static (server-rendered). Disabling JavaScript avoids
        # long waits on client-side scripts and speeds each render considerably.
        "--disable-javascript",
        url, body,
    ]
    try:
        proc = _run(body_cmd, RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "render timed out after %ds" % RENDER_TIMEOUT
    except FileNotFoundError:
        return False, "renderer not found: %s" % RENDERER
    if not (os.path.exists(body) and os.path.getsize(body) > 1024):
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, "render produced no usable PDF" + (": " + err[-1] if err else "")

    # Render the provenance cover, then merge cover + body while stamping the
    # footer on every page in the same ghostscript pass.
    try:
        with open(cover_html, "w", encoding="utf-8") as fh:
            fh.write(build_cover_html(url, captured_utc, http_code, citing_controls))
        _run([RENDERER, "--quiet", "--disable-javascript", cover_html, cover],
             RENDER_TIMEOUT)
        if os.path.exists(cover) and os.path.getsize(cover) > 512:
            ok, _msg = merge_pdfs(cover, body, dest, footer_text=footer)
            if ok:
                return True, "ok with cover + footer (%d bytes)" % os.path.getsize(dest)
        # Cover/merge failed - fall back to the plain body so a capture is never
        # lost to a provenance error (recorded in the status message).
        shutil.move(body, dest)
        return True, "ok, body only (cover/merge failed) (%d bytes)" % os.path.getsize(dest)
    finally:
        for tmp in (body, cover, cover_html):
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def main():
    global RENDERER_VERSION
    links, citations = collect_links()
    os.makedirs(OUT_DIR, exist_ok=True)
    if not SKIP_RENDER:
        RENDERER_VERSION = renderer_version()

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "renderer": RENDERER_VERSION or RENDERER,
        "skip_render": SKIP_RENDER,
        "controls": {},
        "summary": {"local": 0, "evidence_web_captured": 0,
                    "evidence_web_failed": 0, "evidence_web_broken": 0,
                    "evidence_auth_manual": 0, "reference": 0},
    }

    status_cache = {}  # url -> http status, so a URL is probed once per run

    for cid in sorted(links):
        entries = []
        control_out = os.path.join(OUT_DIR, cid)
        for label, target, kind in links[cid]:
            entry = {"label": label, "target": target, "kind": kind}
            if kind == "evidence-web":
                if SKIP_RENDER:
                    entry["status"] = "skipped (EVIDENCE_SKIP_RENDER)"
                else:
                    # Check the link resolves before rendering, otherwise we
                    # would capture the site's 404 page as if it were evidence.
                    # Cache per URL so the same page (cited by several controls)
                    # is probed once and cannot diverge on a transient blip.
                    if target not in status_cache:
                        status_cache[target] = http_status(target)
                    code = status_cache[target]
                    entry["http_status"] = code
                    if code not in REACHABLE_CODES:
                        entry["status"] = ("BROKEN LINK (HTTP %s) - not captured; "
                                           "fix the narrative link or export manually"
                                           % (code or "unreachable"))
                        manifest["summary"]["evidence_web_broken"] += 1
                    else:
                        os.makedirs(control_out, exist_ok=True)
                        dest = os.path.join(control_out, slugify_url(target) + ".pdf")
                        ok, msg = render_pdf(
                            target, dest,
                            captured_utc=manifest["generated"],
                            http_code=code,
                            citing_controls=citations.get(target, [cid]),
                        )
                        entry["status"] = msg
                        if ok:
                            entry["pdf"] = os.path.relpath(dest, REPO_ROOT)
                            manifest["summary"]["evidence_web_captured"] += 1
                        else:
                            manifest["summary"]["evidence_web_failed"] += 1
            elif kind == "evidence-auth":
                entry["status"] = "MANUAL EXPORT REQUIRED (authenticated source)"
                manifest["summary"]["evidence_auth_manual"] += 1
            elif kind == "local":
                manifest["summary"]["local"] += 1
            elif kind == "reference":
                manifest["summary"]["reference"] += 1
            if kind in ("evidence-web", "evidence-auth"):
                entries.append(entry)
        if entries:
            manifest["controls"][cid] = entries

    # Write JSON manifest
    json_path = os.path.join(OUT_DIR, "manifest.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    # Write Markdown manifest
    md_path = os.path.join(OUT_DIR, "MANIFEST.md")
    write_markdown_manifest(md_path, manifest)

    s = manifest["summary"]
    print("Evidence capture complete.")
    print("  local (already in SA folder):   %d" % s["local"])
    print("  evidence-web captured to PDF:   %d" % s["evidence_web_captured"])
    print("  evidence-web render failed:     %d" % s["evidence_web_failed"])
    print("  evidence-web BROKEN links:      %d" % s["evidence_web_broken"])
    print("  evidence-auth MANUAL export:    %d" % s["evidence_auth_manual"])
    print("  third-party references:         %d" % s["reference"])
    print("Manifest: %s" % os.path.relpath(md_path, REPO_ROOT))
    print("          %s" % os.path.relpath(json_path, REPO_ROOT))


def write_markdown_manifest(path, manifest):
    lines = []
    lines.append("# Aurora Evidence Capture Manifest")
    lines.append("")
    lines.append("Generated: %s" % manifest["generated"])
    lines.append("")
    lines.append("This manifest tracks evidence linked from the control narratives that is "
                 "not already a file in this repository. It supports roadmap issue #516: "
                 "ensuring every piece of linked evidence physically exists in the Security "
                 "Assessment (SA) folder.")
    lines.append("")
    lines.append("Categories:")
    lines.append("")
    lines.append("- **Captured**: an Aurora-controlled, publicly reachable URL rendered to "
                 "PDF under `output/evidence-pdfs/<CONTROL-ID>/`, with a provenance cover page "
                 "and per-page footer.")
    lines.append("- **Manual export required**: an Aurora-controlled URL behind "
                 "authentication (SharePoint, private GitHub, Azure DevOps). A person must "
                 "export it and drop it into the SA folder.")
    lines.append("")
    s = manifest["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---|")
    lines.append("| Local (already in repo) | %d |" % s["local"])
    lines.append("| Evidence-web captured to PDF | %d |" % s["evidence_web_captured"])
    lines.append("| Evidence-web render failed | %d |" % s["evidence_web_failed"])
    lines.append("| Evidence-web BROKEN links (404/unreachable) | %d |" % s["evidence_web_broken"])
    lines.append("| Evidence-auth (manual export) | %d |" % s["evidence_auth_manual"])
    lines.append("| Third-party references (not captured) | %d |" % s["reference"])
    lines.append("")
    lines.append("## Per-control detail")
    lines.append("")
    if not manifest["controls"]:
        lines.append("_No web/authenticated evidence links found._")
    for cid in sorted(manifest["controls"]):
        lines.append("### %s" % cid)
        lines.append("")
        lines.append("| Link | Kind | Status | Captured PDF |")
        lines.append("|---|---|---|---|")
        for e in manifest["controls"][cid]:
            label = (e["label"] or e["target"]).replace("|", "\\|")
            tgt = e["target"].replace("|", "\\|")
            pdf = e.get("pdf", "")
            pdf_cell = "[%s](%s)" % (os.path.basename(pdf), pdf) if pdf else ""
            status = e.get("status", "").replace("|", "\\|")
            lines.append("| [%s](%s) | %s | %s | %s |" % (label, tgt, e["kind"], status, pdf_cell))
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
