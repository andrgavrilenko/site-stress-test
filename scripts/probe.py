#!/usr/bin/env python3
"""Black-box HTTP/DNS/TLS probe for a live site. Stdlib only (certifi used when installed).

Usage: probe.py https://example.com [--out DIR] [--burst N] [--sample N] [--api https://api.example.com]

Writes <out>/probe.json and <out>/summary.md plus raw bodies for key pages.
Read-only: GET/HEAD/OPTIONS only, at most --burst parallel requests once.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, random, socket, ssl, subprocess, sys, time, html
import urllib.request, urllib.error, urllib.parse

try:  # Windows consoles default to cp1252; the summary uses arrows and check marks
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa
    pass


def ssl_context():
    """python.org builds on Windows ship without a CA bundle; fall back to certifi when present."""
    ctx = ssl.create_default_context()
    try:
        if not ctx.get_ca_certs():
            import certifi  # type: ignore
            ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa
        pass
    return ctx


CTX = ssl_context()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) site-stress-test/1.0"
API_PATHS = ["/", "/health", "/healthz", "/openapi.json", "/docs", "/redoc", "/swagger", "/graphql", "/metrics", "/robots.txt"]
LOGIN_RE = re.compile(r"(sign-?in|login|auth)", re.I)
SENSITIVE = ["/.env", "/.git/HEAD", "/wp-login.php", "/wp-json/wp/v2/users", "/xmlrpc.php", "/readme.html",
             "/admin", "/api/", "/.well-known/security.txt", "/humans.txt", "/sw.js", "/manifest.webmanifest"]
SEC_HEADERS = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options",
               "referrer-policy", "permissions-policy", "cross-origin-opener-policy"]
HEAD_RE = {
    "lang": r'<html[^>]*\slang="([^"]*)"',
    "title": r"<title>([^<]*)",
    "description": r'<meta\s+name="description"\s+content="([^"]*)"',
    "canonical": r'<link\s+rel="canonical"\s+href="([^"]*)"',
    "og_url": r'<meta\s+property="og:url"\s+content="([^"]*)"',
    "robots_meta": r'<meta\s+name="robots"\s+content="([^"]*)"',
}


def fetch(url, method="GET", headers=None, timeout=20, body=False):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept-Encoding": "identity", **(headers or {})})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read() if body or method == "GET" else b""
            return {"status": r.status, "headers": {k.lower(): v for k, v in r.headers.items()}, "body": data,
                    "ttfb_ms": round((time.perf_counter() - t0) * 1000), "url": r.geturl()}
    except urllib.error.HTTPError as e:
        data = e.read() if body else b""
        return {"status": e.code, "headers": {k.lower(): v for k, v in e.headers.items()}, "body": data,
                "ttfb_ms": round((time.perf_counter() - t0) * 1000), "url": url}
    except ssl.SSLError as e:
        sys.exit(f"TLS error for {url}: {e}\nThis Python has no CA bundle. Run: pip install certifi")
    except Exception as e:  # noqa
        return {"status": 0, "headers": {}, "body": b"", "ttfb_ms": None, "url": url, "error": str(e)[:200]}


def no_redirect_status(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=CTX))
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")
    except Exception as e:  # noqa
        return 0, str(e)[:100]


def md5(b):
    return hashlib.md5(b).hexdigest()[:10]


def head_meta(body):
    s = body.decode("utf-8", "replace")
    out = {k: (re.search(p, s, re.I).group(1) if re.search(p, s, re.I) else None) for k, p in HEAD_RE.items()}
    out["hreflang"] = re.findall(r'hreflang="([^"]*)"\s+href="([^"]*)"', s, re.I)
    out["jsonld_types"] = re.findall(r'"@type"\s*:\s*"(\w+)"', s)[:8]
    out["size"] = len(body)
    out["md5"] = md5(body)
    return out


def nslookup(name, rtype):
    try:
        p = subprocess.run(["nslookup", f"-type={rtype}", name, "1.1.1.1"], capture_output=True, text=True, timeout=15)
        lines = [l.strip() for l in p.stdout.splitlines() if l.strip() and "1.1.1.1" not in l and not l.startswith("Server")]
        return lines[:12]
    except Exception as e:  # noqa
        return [f"error: {e}"]


def tls_info(host):
    try:
        with socket.create_connection((host, 443), timeout=15) as sock:
            with CTX.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
                return {"protocol": ss.version(), "issuer": dict(x[0] for x in cert.get("issuer", [])).get("organizationName"),
                        "not_after": cert.get("notAfter"), "san": [v for k, v in cert.get("subjectAltName", [])][:5]}
    except Exception as e:  # noqa
        return {"error": str(e)[:200]}


def probe_api(api):
    """Separate API host: what is reachable without auth, which headers it sends, how CORS behaves."""
    api = api.rstrip("/")
    out = {"host": api, "paths": {}, "security_headers": {}, "openapi": None, "cors_preflight": None}
    for p in API_PATHS:
        r = fetch(api + p, body=True)
        out["paths"][p] = {"status": r["status"], "ct": (r["headers"].get("content-type") or "")[:40], "size": len(r["body"]),
                           "preview": r["body"][:160].decode("utf-8", "replace").replace("\n", " ") if r["status"] == 200 else ""}
        if p == "/health" or (p == "/" and not out["security_headers"]):
            out["security_headers"] = {k: r["headers"].get(k) for k in SEC_HEADERS}
            out["server"] = r["headers"].get("server")
        if p == "/openapi.json" and r["status"] == 200:
            try:
                o = json.loads(r["body"])
                glob = o.get("security")
                ops, no_sec, tags = 0, [], {}
                for path, item in o.get("paths", {}).items():
                    for m, op in item.items():
                        if m not in ("get", "post", "put", "patch", "delete"):
                            continue
                        ops += 1
                        for t in op.get("tags", ["-"]):
                            tags[t] = tags.get(t, 0) + 1
                        if not (op.get("security") or glob):
                            no_sec.append(f"{m.upper()} {path}")
                out["openapi"] = {"title": o.get("info", {}).get("title"), "paths": len(o.get("paths", {})), "operations": ops,
                                  "without_security": no_sec[:40], "schemes": list(o.get("components", {}).get("securitySchemes", {}).keys()),
                                  "admin_like_tags": {t: n for t, n in tags.items() if "admin" in t.lower() or "internal" in t.lower()}}
            except Exception as e:  # noqa
                out["openapi"] = {"error": str(e)[:100]}
    pf = fetch(api + "/health", method="OPTIONS", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    out["cors_preflight"] = {"status": pf["status"], "acao": pf["headers"].get("access-control-allow-origin"), "acac": pf["headers"].get("access-control-allow-credentials")}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda _: fetch(api + "/health"), range(10)))
    out["burst10_health"] = {"statuses": sorted(set(r["status"] for r in res)), "ttfb_ms": sorted(r["ttfb_ms"] or 0 for r in res),
                             "ratelimit_headers": sorted({k for r in res for k in r["headers"] if "ratelimit" in k or k == "retry-after"})}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="probe_out")
    ap.add_argument("--burst", type=int, default=10)
    ap.add_argument("--sample", type=int, default=15, help="sitemap URLs to sample")
    ap.add_argument("--api", default=None, help="separate API origin to probe, e.g. https://api.example.com")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    u = urllib.parse.urlparse(base)
    host, scheme = u.netloc, u.scheme
    apex = host[4:] if host.startswith("www.") else host
    os.makedirs(a.out, exist_ok=True)
    R = {"target": base, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    # 1. redirects
    R["redirects"] = {v: no_redirect_status(v) for v in [f"http://{apex}/", f"https://{apex}/", f"http://www.{apex}/", f"https://www.{apex}/"]}

    # 2. home + headers
    home = fetch(base + "/", body=True)
    open(os.path.join(a.out, "home.html"), "wb").write(home["body"])
    R["home"] = {"status": home["status"], "ttfb_ms": home["ttfb_ms"], "final_url": home["url"], "meta": head_meta(home["body"]),
                 "server": home["headers"].get("server"), "cache": {k: home["headers"].get(k) for k in ["cache-control", "cf-cache-status", "age", "etag", "x-vercel-cache", "x-cache"]},
                 "security_headers": {k: home["headers"].get(k) for k in SEC_HEADERS},
                 "cors": home["headers"].get("access-control-allow-origin"), "alt_svc": home["headers"].get("alt-svc")}
    # compression check
    gz = fetch(base + "/", headers={"Accept-Encoding": "br, gzip"})
    R["home"]["content_encoding"] = gz["headers"].get("content-encoding")

    # 3. soft-404
    rnd = f"/__probe_{random.randint(10**6, 10**7)}"
    first_status, first_loc = no_redirect_status(base + rnd)
    r404 = fetch(base + rnd, body=True)
    R["soft404"] = {"random_path": rnd, "first_status": first_status, "redirects_to": first_loc, "final_status": r404["status"],
                    "same_body_as_home": md5(r404["body"]) == R["home"]["meta"]["md5"],
                    "redirects_to_login": bool(first_loc and LOGIN_RE.search(first_loc)),
                    "content_type": r404["headers"].get("content-type")}
    # canonical that itself redirects is a finding
    can = R["home"]["meta"].get("canonical")
    if can:
        cs, cl = no_redirect_status(can if can.endswith("/") or "." in can.rsplit("/", 1)[-1] else can)
        R["home"]["canonical_status"] = [cs, cl]
    sens = {}
    for p in SENSITIVE:
        r = fetch(base + p, body=True)
        sens[p] = {"status": r["status"], "ct": (r["headers"].get("content-type") or "")[:40], "size": len(r["body"]),
                   "same_as_home": md5(r["body"]) == R["home"]["meta"]["md5"], "www_auth": r["headers"].get("www-authenticate")}
    img404 = fetch(base + "/img/__probe_missing.png", body=True)
    sens["/img/__probe_missing.png"] = {"status": img404["status"], "ct": (img404["headers"].get("content-type") or "")[:40], "same_as_home": md5(img404["body"]) == R["home"]["meta"]["md5"]}
    R["sensitive_paths"] = sens

    # 4. robots + sitemap
    rob = fetch(base + "/robots.txt", body=True)
    R["robots"] = {"status": rob["status"], "text": rob["body"].decode("utf-8", "replace")[:1500] if rob["status"] == 200 else None}
    sm_urls = re.findall(r"(?im)^sitemap:\s*(\S+)", R["robots"]["text"] or "") or [base + "/sitemap.xml"]
    locs, lastmods = [], []
    for sm in sm_urls[:3]:
        s = fetch(sm, body=True)
        if s["status"] != 200:
            continue
        txt = s["body"].decode("utf-8", "replace")
        sub = re.findall(r"<sitemap>.*?<loc>([^<]+)</loc>", txt, re.S)
        for ss in sub[:5]:
            t2 = fetch(ss, body=True)["body"].decode("utf-8", "replace")
            locs += re.findall(r"<loc>([^<]+)</loc>", t2); lastmods += re.findall(r"<lastmod>([^<]+)</lastmod>", t2)
        locs += re.findall(r"<url>.*?<loc>([^<]+)</loc>", txt, re.S); lastmods += re.findall(r"<lastmod>([^<]+)</lastmod>", txt)
    from collections import Counter
    pat = Counter(re.sub(r"^https?://[^/]+/([^/]*).*", r"\1", l) or "/" for l in locs)
    R["sitemap"] = {"sources": sm_urls[:3], "url_count": len(locs), "lastmod_top": Counter(lastmods).most_common(3), "path_prefixes": pat.most_common(12)}
    sample = random.sample(locs, min(a.sample, len(locs))) if locs else []
    pages = {}
    for l in sample:
        r = fetch(l, body=True)
        m = head_meta(r["body"])
        pages[l] = {"status": r["status"], "lang": m["lang"], "title": m["title"], "canonical": m["canonical"], "og_url": m["og_url"], "md5": m["md5"], "size": m["size"], "hreflang_n": len(m["hreflang"])}
    R["sitemap_sample"] = pages
    dup = Counter(p["md5"] for p in pages.values())
    R["sitemap_sample_dup_bodies"] = dup.most_common(3)

    # 5. latency + burst
    def ttfb(url, n=3):
        return [fetch(url)["ttfb_ms"] for _ in range(n)]
    R["ttfb"] = {base + "/": ttfb(base + "/")}
    if sample:
        R["ttfb"][sample[0]] = ttfb(sample[0])
    with cf.ThreadPoolExecutor(max_workers=a.burst) as ex:
        res = list(ex.map(lambda _: fetch(base + "/"), range(a.burst)))
    R["burst"] = {"n": a.burst, "statuses": Counter(r["status"] for r in res).most_common(), "ttfb_ms": sorted(r["ttfb_ms"] or 0 for r in res)}

    # 6. CORS preflight from foreign origin on an API-looking path if present in robots disallow
    api_path = next((d for d in re.findall(r"(?im)^disallow:\s*(/\S*api\S*)", R["robots"]["text"] or "")), None)
    if api_path:
        pf = fetch(base + api_path.rstrip("/") + "/x", method="OPTIONS", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        R["cors_preflight"] = {"path": api_path, "status": pf["status"], "acao": pf["headers"].get("access-control-allow-origin")}

    # 7. DNS + TLS
    R["dns"] = {"NS": nslookup(apex, "NS"), "A": nslookup(apex, "A"), "AAAA": nslookup(apex, "AAAA"), "MX": nslookup(apex, "MX"),
                "TXT": nslookup(apex, "TXT"), "DMARC": nslookup("_dmarc." + apex, "TXT"), "CAA": nslookup(apex, "CAA")}
    R["tls"] = tls_info(host)

    # 8. separate API host
    if a.api:
        R["api"] = probe_api(a.api)
        R["api"]["dns"] = nslookup(urllib.parse.urlparse(a.api).netloc, "A")
        R["api"]["tls"] = tls_info(urllib.parse.urlparse(a.api).netloc)

    json.dump(R, open(os.path.join(a.out, "probe.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)

    # summary
    L = [f"# Probe summary: {base} ({R['checked_at']})", ""]
    L.append("## Redirects"); L += [f"- `{k}` → {v[0]} {v[1] or ''}" for k, v in R["redirects"].items()]
    h = R["home"]; m = h["meta"]
    L += ["", "## Home", f"- status {h['status']}, TTFB {h['ttfb_ms']} ms, server `{h['server']}`, encoding `{h['content_encoding']}`, cache {h['cache']}",
          f"- lang `{m['lang']}`, title `{m['title']}`, canonical `{m['canonical']}`, og:url `{m['og_url']}`, hreflang {m['hreflang']}",
          f"- security headers: " + ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in h["security_headers"].items()),
          f"- CORS ACAO on HTML: `{h['cors']}`"]
    if h.get("canonical_status"):
        cs = h["canonical_status"]
        L.append(f"- canonical fetch → {cs[0]} {cs[1] or ''}" + ("  **(canonical redirects: point it at the final URL)**" if 300 <= (cs[0] or 0) < 400 else ""))
    s4 = R["soft404"]
    L += ["", "## Soft-404", f"- random path → first {s4['first_status']} {s4['redirects_to'] or ''} → final {s4['final_status']}, same body as home: **{s4['same_body_as_home']}**"
          + ("  **(soft-404 via redirect to login)**" if s4["redirects_to_login"] else "")]
    L += [f"- `{p}` → {v['status']} {v['ct']} same_as_home={v['same_as_home']}" + (f" auth={v['www_auth']}" if v.get('www_auth') else "") for p, v in R["sensitive_paths"].items()]
    sm = R["sitemap"]
    L += ["", "## Sitemap", f"- {sm['url_count']} URLs, lastmod top {sm['lastmod_top']}", f"- prefixes {sm['path_prefixes']}",
          f"- sample of {len(pages)}: statuses {Counter(p['status'] for p in pages.values()).most_common()}, duplicate bodies {R['sitemap_sample_dup_bodies']}",
          f"- sample langs {Counter(p['lang'] for p in pages.values()).most_common()}, with canonical {sum(1 for p in pages.values() if p['canonical'])}/{len(pages)}"]
    L += ["", "## Latency", *(f"- `{k}`: {v} ms" for k, v in R["ttfb"].items()), f"- burst {R['burst']['n']}: {R['burst']['statuses']}, TTFB {R['burst']['ttfb_ms']} (each thread opens its own TLS connection, so spread is mostly handshake cost; look for 429s and for the max, not the mean)"]
    if "cors_preflight" in R:
        L += ["", f"## CORS preflight {R['cors_preflight']}"]
    L += ["", "## DNS / TLS", *(f"- {k}: {v}" for k, v in R["dns"].items()), f"- TLS: {R['tls']}"]
    if "api" in R:
        A = R["api"]
        L += ["", f"## API host {A['host']}", f"- server `{A.get('server')}`, security headers: " + ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in A["security_headers"].items())]
        L += [f"- `{p}` → {v['status']} {v['ct']}" + (f" `{v['preview'][:100]}`" if v["preview"] else "") for p, v in A["paths"].items()]
        if A.get("openapi"):
            o = A["openapi"]
            L.append(f"- OpenAPI public: {o.get('paths')} paths, {o.get('operations')} operations, schemes {o.get('schemes')}, admin-like tags {o.get('admin_like_tags')}, operations without security: {len(o.get('without_security', []))}")
        L += [f"- CORS preflight from foreign origin: {A['cors_preflight']}", f"- burst 10 /health: statuses {A['burst10_health']['statuses']}, TTFB {A['burst10_health']['ttfb_ms']}, rate-limit headers {A['burst10_health']['ratelimit_headers'] or 'none'}",
              f"- DNS A: {A.get('dns')}", f"- TLS: {A.get('tls')}"]
    L += ["", "## Robots.txt", "```", (R["robots"]["text"] or "(none)")[:800], "```"]
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
