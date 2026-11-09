# Per-area checklist

Open this when unsure whether an area is covered. Not every item applies; skip what does not and do not pad the report with N/A rows.

## Availability and HTTP
- http→https and www→apex (or reverse) redirects, one hop, 301.
- Unknown paths return a real 404 (not 200 with the home page). Check an HTML path, an image path, a JSON path, `/api/zzz`.
- Sensitive paths (`/.env`, `/.git/HEAD`, `/wp-login.php`, `/xmlrpc.php`) do not return 200 with content; a 200 that is really the SPA shell is still a soft-404 and will attract scanners.
- Admin surfaces: what protects them (Basic Auth, SSO, IP allowlist)? `WWW-Authenticate` realm names leak product names.
- `security.txt`, `robots.txt`, `sitemap.xml`, `manifest.webmanifest`, `sw.js` exist where the HTML references them.

## Security headers and transport
- HSTS (with includeSubDomains, ideally preload), CSP (at least `frame-ancestors`, `object-src`), `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`.
- `Access-Control-Allow-Origin: *` on HTML or on APIs that use credentials is a smell.
- Third-party scripts without SRI from CDNs (unpkg, jsdelivr, cdnjs): one compromised CDN = full page takeover.
- TLS 1.2+, cert expiry > 30 days, auto-renewal, HTTP/2 or 3.

## API behaviour
- Input validation: garbage IDs → 400, not 500. Lists: find the length that breaks the server; compare with the client's own cap.
- Platform error pages (Cloudflare 1101, Vercel 500 page, raw stack traces) = unhandled exception.
- Unauthenticated access to data that is monetised or per-user.
- Write endpoints: GET → 404/405, foreign-origin preflight → denied, no CSRF via simple requests, honeypot or Turnstile/captcha on public forms.
- Rate limiting on `/api/*` (expect 429 at some point in a 20-request burst, or a documented reason it is not needed).
- Client-generated identifiers (device IDs, session IDs) trusted by the server for counting (likes, votes, reports) = trivial inflation.

## SEO and indexing
- Each sitemap URL returns 200 with its own title, description, canonical equal to the sitemap URL, correct `lang`.
- Test with a Googlebot UA too: some sites render only for bots.
- Language variants: `/en/` serves `lang="en"`, English meta, `og:locale`; hreflang set complete with `x-default`.
- `lastmod` real, not "today" for everything.
- `og:url`, `og:image` per page, not the root.
- Structured data types present and plausible (Organization, WebSite, ItemList, FAQPage, LocalBusiness/Restaurant).
- `robots.txt` blocks admin/API, allows the rest; AI crawler stanzas consistent.

## Mobile and UX (browser pass)
- Fresh profile: onboarding, consent, first-load storage. What is created before consent, what leaves the device before consent.
- Overlaps: consent banner over CTAs, sheet handles over buttons, FABs over list items. `elementFromPoint` at button centres.
- Tap targets ≥ 44 px, no horizontal overflow (`scrollWidth > innerWidth`), text not clipped at 375 px.
- Duplicate network calls after one user action (count them in the network log).
- Console errors and warnings on load and after main interactions.
- i18n leaks: data requested with the wrong `lang`, mixed-language strings, wrong label reused (`Copy address` on a phone number).
- Accessibility basics: duplicated numbers for screen readers (animated counters), buttons without names, skip link, focus after dialogs.
- Desktop-only regressions: panels that collapse on map pan, hover-only controls.

## PWA
- Manifest valid, icons present, `theme-color` matches, splash images referenced exist.
- Service worker: precache list resolvable, navigation strategy with timeout and offline fallback, `/api/*` excluded, version bump strategy, cache caps for tiles/images.

## Hosting and infrastructure
- Identify every layer with evidence: DNS provider, CDN/edge, TLS issuer, compute (platform headers and error pages), storage hints, static asset caching, email (MX/SPF/DKIM/DMARC), telemetry (NEL, RUM).
- Edge cache actually used? `cf-cache-status: DYNAMIC` on cacheable JSON/HTML means every request executes compute.
- Third-party dependencies without SLA: tile servers, public geocoders, demo routing servers, CDNs. What breaks when each is down, and for whom (new vs returning users with SW cache).
- Latency from a stated vantage point, parallel burst without degradation, no 429 where there should be none.
- Cost multipliers: duplicate calls, uncached data, crashes that can be triggered externally.

## Data and content
- Counts consistent across FAQ, landing pages, data files and UI.
- Duplicate records (name + coordinates), records outside the expected bounding box, missing required fields.
- Demo/preview flags reachable by URL (`?promo=demo`) that render fake content on a real entity.
- Stale data markers: "built" dates, "fetched" timestamps, "updated" footers.

## Legal (only when asked)
- Controller identity and contact, legal basis per processing, retention periods, third-country transfers, user rights, supervisory authority.
- Cookie/storage consent matches behaviour (localStorage counts as storage under ePrivacy).
- Terms for paying customers if anything is sold; DSA contact points if users post content; licences for third-party data (ODbL, API ToS).
