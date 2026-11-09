# <Site>: pre-launch stress test

Checked: <date>, <iterations>. Target: <URL> (<build/version marker if visible>).
Method: external HTTP probes (curl/probe.py), bundle and data analysis, browser pass in <browsers and viewports>. Raw responses in `raw/`.

What was written to production: <none | exact list with undo>.
Scope: <technical only | technical + legal>.

Severity: 🔴 before launch · 🟠 first weeks · 🟡 when possible.

---

## 1. Bugs found in the browser

| # | Sev | Problem | How reproduced | What to do |
|---|---|---|---|---|
| B1 | 🔴 | … | … | … |

What works: <one paragraph listing flows that passed, so the owner knows what not to touch>.

## 2. Security

| # | Sev | Problem | What to do |
|---|---|---|---|
| S1 | 🔴 | … | … |

What is in order: <validation, CORS, honeypots, consent gating…>.

## 3. Infrastructure and hosting

### 3.1. Topology
| Layer | What is deployed | Evidence |
|---|---|---|
| DNS | … | … |
| TLS / L7 | … | … |
| Compute | … | … |
| Storage | … | … |
| Static assets | … | … |
| Third parties | … | … |
| Client / PWA | … | … |
| Email | … | … |

### 3.2. Measurements
Vantage point, edge PoP, protocol. Table: metric, result, assessment.

### 3.3. Conclusions
Is the platform adequate? Then the risks in how the app uses it, each with a fix.

## 4. SEO and indexing

| # | Sev | Problem | What to do |
|---|---|---|---|

## 5. Data and content

| # | Sev | Problem |
|---|---|---|

## Minimal pre-launch checklist
1. …
2. …
