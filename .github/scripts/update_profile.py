#!/usr/bin/env python3
"""Keeps the profile README alive.

* Rewrites the "Current Project" row and the project table in README.md
  from the owner's public repositories (newest repo = current project).
* Regenerates assets/stats.svg, assets/streak.svg and assets/langs.svg so the
  profile never depends on third-party stat servers.

Every network step is wrapped: if something fails, the previous file is kept.
Set MOCK_API=<json file> to run offline (used for local testing).
"""
import html, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "fleur12")
PROFILE_REPO = os.environ.get("PROFILE_REPO", OWNER).lower()
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MOCK = os.environ.get("MOCK_API")
ROOT = os.environ.get("OUT_DIR", ".")

# optional hand-written blurbs; anything not listed is described from GitHub
CURATED = {}
if os.path.exists(os.path.join(ROOT, "projects.json")):
    CURATED = json.load(open(os.path.join(ROOT, "projects.json"), encoding="utf-8"))

BG, BORDER, TITLE, TEXT, SUB, GOLD, RING = "#1f5040", "#399d65", "#a6de85", "#f4f0b4", "#cfe9c0", "#fde047", "#a6de85"
LANG_COLORS = ["#fde047", "#a6de85", "#72bf8c", "#f4f0b4", "#c4ccb0", "#d4a373", "#8ecae6"]


def api(path, graphql=None):
    if MOCK:
        data = json.load(open(MOCK, encoding="utf-8"))
        return data["graphql"] if graphql else data[path.split("?")[0]]
    url = "https://api.github.com/graphql" if graphql else "https://api.github.com" + path
    req = urllib.request.Request(url, data=json.dumps(graphql).encode() if graphql else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-updater")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def short(s, n=90):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def ago(iso):
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    return d.strftime("%d %b %Y")


def replace_block(text, tag, body, inline=False):
    pat = re.compile(r"(<!--%s_START-->).*?(<!--%s_END-->)" % (tag, tag), re.S)
    if not pat.search(text):
        print("marker missing:", tag)
        return text
    sep = "" if inline else "\n"
    return pat.sub(lambda m: m.group(1) + sep + body + sep + m.group(2), text)


def card(w, h, inner):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'font-family="Segoe UI,Ubuntu,Arial,sans-serif"><rect x="1" y="1" width="%d" height="%d" rx="6" '
            'fill="%s" stroke="%s" stroke-width="1.5"/>%s</svg>' % (w, h, w, h, w - 2, h - 2, BG, BORDER, inner))


def write(name, content):
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "assets", name), "w", encoding="utf-8") as f:
        f.write(content)


def main():
    repos = [r for r in api("/users/%s/repos?per_page=100&type=owner" % OWNER)
             if not r["fork"] and r["name"].lower() != PROFILE_REPO and not r.get("archived")]
    if not repos:
        print("no repositories found; nothing to do")
        return
    by_created = sorted(repos, key=lambda r: r["created_at"], reverse=True)
    by_pushed = sorted(repos, key=lambda r: r["pushed_at"], reverse=True)
    current = by_created[0]

    # ---------- README ----------
    readme_path = os.path.join(ROOT, "README.md")
    text = open(readme_path, encoding="utf-8").read()
    text = replace_block(text, "CURRENT", "[%s](%s)" % (current["name"].replace("-", " ").replace("_", " "), current["html_url"]), inline=True)
    rows = ["| Project | About | Language | Updated |", "|---|---|---|---|"]
    for r in by_pushed:
        about = CURATED.get(r["name"], {}).get("about") or r.get("description") or "—"
        rows.append("| [**%s**](%s) | %s | %s | %s |" % (
            r["name"], r["html_url"], short(about.replace("|", "/"), 150), r.get("language") or "—", ago(r["pushed_at"])))
    text = replace_block(text, "PROJECTS", "\n".join(rows))
    open(readme_path, "w", encoding="utf-8").write(text)

    # ---------- stats card ----------
    try:
        user = api("/users/%s" % OWNER)
        stars = sum(r["stargazers_count"] for r in repos)
        forks = sum(r["forks_count"] for r in repos)
        lines = [("⭐ Stars earned", stars), ("📁 Public repositories", len(repos)),
                 ("🍴 Forks", forks), ("👥 Followers", user.get("followers", 0)),
                 ("🗓️ On GitHub since", (user.get("created_at") or "")[:4])]
        body = '<text x="22" y="36" font-size="18" font-weight="700" fill="%s">%s\'s GitHub Stats</text>' % (TITLE, esc(user.get("name") or OWNER))
        for i, (k, v) in enumerate(lines):
            y = 68 + i * 22
            body += '<text x="22" y="%d" font-size="13.5" fill="%s">%s</text><text x="235" y="%d" font-size="13.5" font-weight="700" fill="%s">%s</text>' % (y, TEXT, esc(k), y, TEXT, esc(v))
        write("stats.svg", card(395, 170, body))
    except Exception as e:
        print("stats skipped:", e)

    # ---------- languages card ----------
    try:
        totals = {}
        for r in repos:
            for lang, n in api("/repos/%s/%s/languages" % (OWNER, r["name"])).items():
                totals[lang] = totals.get(lang, 0) + n
        if totals:
            totals = {k.replace("Jupyter Notebook", "Jupyter"): v for k, v in totals.items()}
            top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
            tot = sum(v for _, v in top)
            body = '<text x="20" y="32" font-size="17" font-weight="700" fill="%s">Most Used Languages</text>' % TITLE
            body += '<rect x="20" y="46" width="300" height="9" rx="4" fill="#2d6a50"/>'
            x = 20.0
            for i, (lang, v) in enumerate(top):
                w = 300.0 * v / tot
                body += '<rect x="%.1f" y="46" width="%.1f" height="9" fill="%s"/>' % (x, w, LANG_COLORS[i % len(LANG_COLORS)])
                x += w
            for i, (lang, v) in enumerate(top):
                cx, cy = 26 + (i % 2) * 150, 78 + (i // 2) * 22
                body += '<circle cx="%d" cy="%d" r="5" fill="%s"/><text x="%d" y="%d" font-size="12" fill="%s">%s %d%%</text>' % (
                    cx, cy, LANG_COLORS[i % len(LANG_COLORS)], cx + 12, cy + 4, TEXT, esc(lang), round(100 * v / tot))
            write("langs.svg", card(340, 150, body))
    except Exception as e:
        print("languages skipped:", e)

    # ---------- streak card ----------
    try:
        q = {"query": "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}",
             "variables": {"l": OWNER}}
        cal = api("", q)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        days = sorted((d["date"], d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"])
        today = date.today().isoformat()
        days = [d for d in days if d[0] <= today]
        longest = run = 0
        for _, n in days:
            run = run + 1 if n else 0
            longest = max(longest, run)
        cur, i = 0, len(days) - 1
        if i >= 0 and days[i][1] == 0:  # today may not have a contribution yet
            i -= 1
        while i >= 0 and days[i][1] > 0:
            cur += 1
            i -= 1
        body = ""
        for cx, big, label, sub in ((66, cal["totalContributions"], "Contributions", "Last 12 months"),
                                    (328, longest, "Longest Streak", "Last 12 months")):
            body += ('<g text-anchor="middle"><text x="%d" y="80" font-size="28" font-weight="700" fill="%s">%s</text>'
                     '<text x="%d" y="106" font-size="12.5" fill="%s">%s</text><text x="%d" y="124" font-size="10.5" fill="%s">%s</text></g>'
                     % (cx, TEXT, big, cx, TITLE, label, cx, SUB, sub))
        body += ('<g text-anchor="middle"><circle cx="197" cy="78" r="40" fill="none" stroke="%s" stroke-width="5"/>'
                 '<text x="197" y="88" font-size="30" font-weight="700" fill="%s">%d</text>'
                 '<path d="M197,24 c8,10 14,14 4,26 c-1,-8 -8,-10 -12,-4 c-4,-8 4,-14 8,-22z" fill="%s"/>'
                 '<text x="197" y="138" font-size="12.5" font-weight="600" fill="%s">Current Streak</text></g>' % (RING, TEXT, cur, GOLD, TITLE))
        body += '<line x1="132" y1="40" x2="132" y2="130" stroke="%s" opacity=".6"/><line x1="263" y1="40" x2="263" y2="130" stroke="%s" opacity=".6"/>' % (BORDER, BORDER)
        write("streak.svg", card(395, 170, body))
    except Exception as e:
        print("streak skipped:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never fail the workflow over cosmetics
        print("update skipped:", e)
        sys.exit(0)
