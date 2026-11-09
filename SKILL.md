---
name: site-stress-test
description: Black-box pre-launch stress test of a live website or web app from the outside, with evidence for every finding. Covers HTTP/TLS/DNS, soft-404s, security headers, API abuse (oversized inputs, missing rate limits, unauthenticated data), SEO (sitemap vs real pages, canonical, hreflang, lang), PWA/service worker, hosting and edge caching (Cloudflare and friends), then a hands-on browser pass on desktop and in phone emulation (overlaps, tap targets, duplicate requests, console errors, likes/forms/map interactions). Use it whenever the user asks to check, audit, stress-test or QA a site before launch, "посмотри сайт", "проверь сайт", "стресс-тест", "что сломано", "найди косяки", "готов ли к запуску", or gives a URL and asks what is wrong with it, even if they do not say "audit". Not for Lighthouse-score tuning or source-code review of a repo (use code review for that).
---

# Site stress test

You are the last reviewer before launch. The owner wants a list of things that will break, embarrass them, or cost money, each with proof and a fix. You have no source access by default: everything is observed from outside, the way a user, a crawler, or an attacker sees it.

## Ground rules

- **Read-only on production.** GET freely. Write (likes, forms, votes, subscriptions) only when the user asks you to "play with" a feature, and then once, with a visible undo (like → unlike, favourite → remove). Never submit contact forms, subscriptions or reports on behalf of a fake person. Say in the report exactly what you wrote and that you reverted it.
- **No DoS.** Bursts of 10–20 parallel requests are fine to measure latency and look for 429s. Nothing bigger, nothing repeated in a loop. If a single request crashes the backend (500 from the platform), report it; do not send it ten more times.
- **Evidence or it did not happen.** Every finding carries how you saw it (command, request, screenshot, DOM query). When you cannot reproduce something, say "not verified" instead of guessing. When your own click missed a 10-px marker, that is your miss, not their bug: retry precisely before reporting.
- **Scope follows the user.** Default scope is technical: availability, security, SEO, UX/mobile, hosting, data consistency. Legal and business items (GDPR texts, company identity, B2B terms, licences) go in only if the user asks for "legal" or "everything"; many owners explicitly do not want them in an engineering stress test.
- **Re-verify before you re-report.** If the user says "check yourself again", re-run the key probes rather than re-reading your notes: thresholds move (a "500 IDs" crash may really start at 100).

## Workflow

Work in the project folder the user is in: `<project>/<site>_audit/raw/` for raw responses, `<project>/<site>_audit/REPORT.md` for the report. Keep the task list visible; the owner follows progress there.

### 1. Recon (5 min)

Run the bundled probe first; it does the boring HTTP part in one go and writes JSON + a summary:

```bash
python <skill-dir>/scripts/probe.py https://example.com --out <project>/<site>_audit/raw --burst 10
```

It covers: redirects (http→https, www), response headers and security headers, soft-404 detection (random path and sensitive paths like `/.env`, `/wp-login.php` compared by body hash), robots.txt and sitemap parse with a status sample, per-page `<html lang>`, title, description, canonical, hreflang, og:url, TTFB over 3 runs, a small parallel burst, DNS (NS, A/AAAA, MX, SPF, DMARC), TLS issuer/expiry, compression and cache status. Read `summary.md` from the output folder, then look at the raw files for anything surprising.

Then download the app bundle (`app.js`, `sw.js`, manifest) and grep it: API endpoints (`/api/`), third-party hosts, `localStorage`/`cookie`, consent logic, analytics, clipboard, geolocation. The bundle tells you what the API accepts before you touch it.

### 2. API abuse, gently

For each GET endpoint found in the bundle:
- Empty, garbage and oversized inputs (`id='"<x>`, 100 / 500 IDs in a list). A platform error page (Cloudflare `error code: 1101`, Vercel `FUNCTION_INVOCATION_FAILED`) means an unhandled exception: find the exact threshold by bisection, then stop.
- Compare the client's own limits in the bundle with the server's: `slice(0, 120)` on the client plus a crash at 100 on the server is a bug real users hit, not just an attack.
- Does any endpoint hand out data that is sold or private (per-business stats, user lists) without auth?
- POST endpoints: GET them (should be 404/405), send an OPTIONS preflight from a foreign Origin (should not be allowed).
- Look for rate limiting: a 10–20 request burst with no 429 and no slowdown means there is none.

### 3. Browser pass

Use the built-in browser pane for phone emulation (mobile preset, 375×812, touch UA) and the user's Chrome for a real desktop run. Clear state first: a fresh profile shows the onboarding, consent and first-load behaviour the owner's own browser hides.

Check, in this order, taking a screenshot at each state:
1. First load: console errors, network waterfall, what is created in `localStorage` before any consent, which requests carry IDs.
2. Consent/onboarding: overlap of banners and buttons, whether the privacy-preserving choice really stops the requests it claims to stop.
3. Core flow (search, list, detail, map): count duplicate requests after one action; `elementFromPoint` at the centre of every primary button to catch invisible overlays and overlapping tap targets; `scrollWidth > innerWidth` for horizontal overflow.
4. Interactions the owner cares about (likes, favourites, map pan, "search this area"): do them once, read the network response, check the counter and storage, undo.
5. i18n: the English page should request English data; compare `lang`, title, og tags served vs rendered.
6. Menu, settings, "delete my data", language and theme switches.

Canvas maps (MapLibre, Leaflet GL) ignore imprecise clicks: zoom a screenshot region at scale 1 to get exact pixels, or centre the map on a known item ("show on map") and click the centre.

### 4. Hosting and infrastructure

Describe the stack as a table of layers with the evidence for each: DNS provider, edge/CDN, TLS (issuer, expiry, protocols), compute (Workers/Lambda/Vercel/VPS: platform error pages and headers give it away), storage hints (parameter limits, latency), static asset caching (`cf-cache-status`, `age`, `etag`), third-party dependencies with no SLA (tile servers, public geocoders, unpkg), PWA/service-worker strategy, email (MX, SPF, DKIM, DMARC). Measure TTFB and a burst from where you are and state the vantage point and the edge PoP. Hosting findings are usually about how the app uses the platform (dynamic responses that should be cached, duplicate calls that multiply the bill, missing rate limits), not about the platform itself; say so when that is the case.

### 5. Report

Write `REPORT.md` in the user's language using `references/report-template.md`. Severity: 🔴 before launch, 🟠 first weeks, 🟡 when possible. Every row: problem, how reproduced, what to do. Include a "what works" paragraph: the owner needs to know what not to touch. End with a numbered minimal pre-launch checklist of 5–7 items. Send the file to the user and keep the raw folder.

`references/checklist.md` has the long list of what to look at per area; open it when you are unsure whether you have covered an area.

## Things that look like bugs but are not

- Consent already set to "necessary only" in the owner's own browser profile is their earlier choice, not a default. Check in a clean profile.
- Screenshot timeouts in the Chrome extension while the tab is in the background are a tooling limit; JS still executes. Do not report a "frozen renderer".
- "The page wrote to the clipboard" notes from the browser pane during map drags are false positives when the clipboard is empty afterwards. Check with `Get-Clipboard` before reporting.
- A "search this area" button that appears only after a large pan is a UX threshold question, not a failure; read the code for the threshold before calling it broken.
