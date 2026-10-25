#!/usr/bin/env python3
"""
Publish TakeHold's approved Soro (app.trysoro.com) articles as real blog pages.

The site is static (GitHub Pages), so Soro's browser widget would leave the
articles at /blog?post=..., which Google reads poorly. Instead this pulls the
public feed of PUBLISHED articles (drafts never appear in it), writes each new
one as blog/<slug>.html in the same design as the hand-written posts, adds its
card to blog/index.html and its URL to sitemap.xml, then commits and pushes.

    python3 scripts/soro_sync.py            # publish anything new
    python3 scripts/soro_sync.py --dry-run  # show what would be published

Safe to run any number of times: an article whose page exists is skipped.
"""
import html, json, math, re, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "blog"
TEMPLATE = BLOG / "how-to-get-on-first-page-of-google.html"
FEED = "https://app.trysoro.com/api/embed/d95afc25-b041-4db7-87d1-66323455ad48"
SITE = "https://takeholdmedia.com"
DRY = "--dry-run" in sys.argv


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TakeHold-soro-sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def articles():
    # Soro's CDN holds the bare address; a changing value gets the current list.
    js = fetch(f"{FEED}?v={int(time.time())}")
    m = re.search(r"var SORO_ARTICLES = (\[[\s\S]*?\]);\s*\n", js)
    return [a for a in json.loads(m.group(1)) if a.get("slug") and a.get("title")] if m else []


def body_html(a):
    raw = a.get("content") or json.loads(fetch(f"{FEED}/article/{a['id']}")).get("content") or ""
    raw = re.sub(r"<script[\s\S]*?</script>", "", raw, flags=re.I)
    raw = re.sub(r"<(iframe|object|embed)[\s\S]*?>", "", raw, flags=re.I)
    raw = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", raw, flags=re.I)
    # The page has its own H1 (the title); keep the article's headings below it.
    return re.sub(r"<h1([^>]*)>", r"<h2\1>", raw, flags=re.I).replace("</h1>", "</h2>")


def month(a):
    try:
        return time.strftime("%B %Y", time.strptime(a["isoDate"][:10], "%Y-%m-%d"))
    except Exception:
        return a.get("date", "")


def page(a, body):
    t = TEMPLATE.read_text()
    head, rest = t.split('<div class="article-prose">', 1)
    tail = rest[rest.index("<!-- Sidebar -->"):]
    E = lambda s: html.escape(s or "", quote=True)
    words = len(re.sub(r"<[^>]+>", " ", body).split())
    mins = max(3, math.ceil(words / 220))
    head = re.sub(r"<title>[\s\S]*?</title>", f"<title>{E(a['title'])} | TakeHold Media</title>", head, 1)
    head = re.sub(r'<meta name="description" content="[^"]*"', f'<meta name="description" content="{E(a.get("excerpt"))}"', head, 1)
    head = head.replace("</head>", f'  <link rel="canonical" href="{SITE}/blog/{a["slug"]}.html" />\n</head>', 1)
    head = re.sub(r"<span>SEO</span>(\s*</div>\s*<span class=\"article-cat\">)SEO", r"<span>Guides</span>\1Guides", head, 1)
    head = re.sub(r"<h1>[\s\S]*?</h1>", f"<h1>{E(a['title'])}</h1>", head, 1)
    head = re.sub(r'(<div class="article-meta">\s*<span>)[^<]*(</span>[\s\S]*?<span>)[^<]*( min read</span>| read</span>)',
                  lambda m: f"{m.group(1)}{month(a)}{m.group(2)}{mins} min read</span>", head, 1)
    img = a.get("image") or ""
    head = re.sub(r'(<div class="article-hero-img">\s*<img src=")[^"]*(" alt=")[^"]*(")',
                  lambda m: f"{m.group(1)}{E(img)}{m.group(2)}{E(a['title'])}{m.group(3)}", head, 1)
    if not img:
        head = re.sub(r'<div class="article-hero-img">[\s\S]*?</div>\s*', "", head, 1)
    return f'{head}<div class="article-prose">\n\n{body}\n\n        </div>\n\n        {tail}'


def card(a):
    E = lambda s: html.escape(s or "", quote=True)
    img = f'<img src="{E(a["image"])}" alt="{E(a["title"])}" loading="lazy" />' if a.get("image") else ""
    return f'''        <a href="{a["slug"]}.html" style="text-decoration:none;">
          <div class="blog-card">
            <div class="blog-card-img">
              {img}
            </div>
            <div class="blog-card-body">
              <span class="blog-card-cat">Guides</span>
              <h3>{E(a["title"])}</h3>
              <p>{E(a.get("excerpt"))}</p>
              <div class="blog-meta">{month(a)}</div>
            </div>
          </div>
        </a>

'''


def main():
    new = [a for a in articles() if not (BLOG / f"{a['slug']}.html").exists()]
    if not new:
        print("Nothing new to publish.")
        return
    index = (BLOG / "index.html").read_text()
    sitemap = (ROOT / "sitemap.xml").read_text()
    for a in sorted(new, key=lambda x: x.get("isoDate", "")):
        print(("WOULD PUBLISH " if DRY else "Publishing ") + a["slug"])
        if DRY:
            continue
        (BLOG / f"{a['slug']}.html").write_text(page(a, body_html(a)))
        index = index.replace('<div class="blog-grid">\n', '<div class="blog-grid">\n' + card(a), 1)
        url = f"{SITE}/blog/{a['slug']}.html"
        if url not in sitemap:
            sitemap = sitemap.replace("</urlset>", f"  <url>\n    <loc>{url}</loc>\n    <lastmod>{a.get('isoDate', '')[:10]}</lastmod>\n  </url>\n</urlset>", 1)
    if DRY:
        return
    (BLOG / "index.html").write_text(index)
    (ROOT / "sitemap.xml").write_text(sitemap)
    git = lambda *c: subprocess.run(["git", "-C", str(ROOT), *c], check=True)
    git("add", "blog", "sitemap.xml")
    git("commit", "-m", "Publish from Soro: " + ", ".join(a["title"] for a in new))
    git("push", "origin", "main")
    print(f"Published {len(new)} article(s).")


if __name__ == "__main__":
    main()
