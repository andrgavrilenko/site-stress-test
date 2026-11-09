# site-stress-test

A Claude Code skill for a black-box pre-launch stress test of a live website or web app.
It works from the outside, the way a user, a crawler or an attacker sees the site, with no
source access by default. The pass covers HTTP, TLS and DNS, soft-404s, security headers,
API abuse (oversized inputs, missing rate limits, unauthenticated data), SEO (sitemap versus
real pages, canonical, hreflang, `lang`), PWA and service worker, hosting and edge caching,
and then a hands-on browser pass on desktop and in phone emulation. Every finding carries
the evidence behind it and a fix. The result is a `REPORT.md` the site owner can act on
before launch.

The skill was built from a real pre-launch audit of a city guide app and smoke-tested on it.

## What is in the repository

| Path | Purpose |
|---|---|
| `SKILL.md` | The skill: ground rules, the five-step workflow, and a list of things that look like bugs but are not. |
| `scripts/probe.py` | A read-only HTTP, DNS and TLS probe. Standard library only, no dependencies. |
| `references/checklist.md` | A per-area checklist to open when you are unsure whether an area is covered. |
| `references/report-template.md` | The structure of the final `REPORT.md`. |

## Workflow

1. **Recon.** Run `probe.py`, read its `summary.md`, then download the app bundle and grep it
   for API endpoints, third-party hosts, storage and consent logic. The bundle tells you what
   the API accepts before you touch it.
2. **API abuse, gently.** Empty, garbage and oversized inputs on each GET endpoint found in
   the bundle. Compare client-side limits with server-side ones. Check what the API hands out
   without auth, how write endpoints respond to GET and to a foreign-origin preflight, and
   whether any rate limiting exists.
3. **Browser pass.** Fresh profile, phone emulation and a real desktop run: console errors,
   first-load storage, consent overlap, duplicate requests after one action, invisible
   overlays over tap targets, horizontal overflow, i18n leaks, the interactions the owner
   cares about (done once, then undone).
4. **Hosting and infrastructure.** A table of layers with evidence for each: DNS provider,
   edge and CDN, TLS, compute, storage hints, static asset caching, third parties without an
   SLA, service worker strategy, email records. TTFB and a small burst from a stated vantage
   point.
5. **Report.** `REPORT.md` in the user's language, from the template. Severity on three
   levels (before launch, first weeks, when possible), a "what works" paragraph, and a short
   numbered pre-launch checklist.

## The probe script

`scripts/probe.py` does the boring HTTP part in one go and writes `probe.json`, `summary.md`
and the raw bodies of key pages to the output folder. It checks:

- redirects between http, https, www and apex, without following them;
- the home page: status, TTFB, server header, compression, cache headers, security headers
  (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy,
  COOP), CORS on HTML, Alt-Svc;
- soft-404 detection: a random path and a list of sensitive paths (`/.env`, `/.git/HEAD`,
  `/wp-login.php`, `/xmlrpc.php`, `/admin`, `/api/` and others) compared with the home page
  by body hash, plus a missing image path;
- `robots.txt`, the sitemaps it names (or `/sitemap.xml`), URL count, `lastmod` distribution,
  path prefixes, and a random sample of pages with their status, `lang`, title, canonical,
  `og:url` and hreflang count, with duplicate-body detection across the sample;
- TTFB over three runs for the home page and one sampled page, then one parallel burst of
  `--burst` requests, reporting statuses and the TTFB spread;
- a CORS preflight from a foreign origin against an API path if `robots.txt` disallows one;
- DNS: NS, A, AAAA, MX, TXT (SPF), DMARC and CAA records via `nslookup` against 1.1.1.1;
- TLS: protocol, issuer, expiry and the first SANs.

Run it from the skill folder, or from wherever you cloned this repository:

```bash
python scripts/probe.py https://example.com --out audit/raw --burst 10
```

Options: `--out DIR` (default `probe_out`), `--burst N` parallel requests, once (default 10),
`--sample N` sitemap URLs to fetch (default 15). The script sends GET, HEAD and OPTIONS only,
and the burst runs exactly once. It needs Python 3.8 or newer and `nslookup` on the PATH.

## Install

Clone the repository into your Claude Code skills folder:

```bash
git clone https://github.com/andrgavrilenko/site-stress-test ~/.claude/skills/site-stress-test
```

Or copy the four files by hand so that `~/.claude/skills/site-stress-test/SKILL.md` exists
next to `scripts/` and `references/`. The skill is plain markdown plus one Python script, so
any agent that reads `SKILL.md` files can use it; the browser pass in step 3 assumes the
browser tools of the Claude desktop app (the built-in browser pane for phone emulation and
Claude in Chrome for a real desktop run) and needs adapting elsewhere.

The repository also follows the layout of the [skills](https://github.com/vercel-labs/skills)
CLI, which discovers a `SKILL.md` at the repository root:

```bash
npx skills add andrgavrilenko/site-stress-test -a claude-code
```

Once installed, the skill loads when you ask Claude Code to check, audit, stress-test or QA a
site before launch, or give it a URL and ask what is wrong with it. The description also
carries a few Russian trigger phrases ("проверь сайт", "что сломано", "готов ли к запуску")
on purpose, so the skill fires for a Russian-speaking owner too.

## Ground rules

These are written into `SKILL.md` and the agent is expected to follow them:

- **Read-only on production.** GET freely. Write actions (likes, forms, votes) only when the
  owner asks to "play with" a feature, then once, with a visible undo. Never submit contact
  forms or subscriptions on behalf of a fake person. The report says exactly what was written
  and that it was reverted.
- **No denial of service.** Bursts of 10 to 20 parallel requests are the ceiling, and they
  run once. If one request crashes the backend, report it, do not repeat it.
- **Evidence for every finding.** Each row of the report says how it was observed: command,
  request, screenshot or DOM query. What could not be reproduced is marked "not verified".
- **Technical scope by default.** Legal and business items (GDPR texts, company identity,
  terms, licences) go in only when the owner asks for "legal" or "everything".

Run this only against sites you own or have written permission to test.

## How it differs from similar skills

Several public skills cover pre-launch checks, all MIT-licensed on GitHub:
[samber/cc-skills](https://github.com/samber/cc-skills) has a `site-launch-checklist`,
[jalaalrd/full-stack-audit](https://github.com/jalaalrd/full-stack-audit) audits a code base
across layers, and [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills)
collects performance and quality guidance. Those are mostly checklists the agent reads
through. This skill is evidence-led instead: a bundled probe script produces measurements
first, the agent then abuses the API and drives a real browser on desktop and in phone
emulation, and the report is built from what was observed rather than from a list of things
to look for. It does not try to tune Lighthouse scores or review the repository source; use
a code-review skill for that.

## License

MIT, see [LICENSE](LICENSE).
