---
date: 2026-09-24
slug: datacenter-ip-blocking
categories:
  - Measurements
title: Which job sites block you from a datacenter IP (measured)
description: >-
  Measured on 2026-09-24 from an AWS IP (AS16509, us-west-2): Indeed, Get on Board
  and the LinkedIn Voyager API return 403, while every public ATS job-board API
  returns 200.
---

# Which job sites block you from a datacenter IP (measured)

If you write a job scraper and run it on a server, some sources will answer 403 and
others will not. This is not folklore. On 2026-09-24 I measured both groups from
the same IP within the same few minutes, and the split is clean. Here are the
numbers.

<!-- more -->

## Setup

Every request left an AWS instance in `us-west-2`, that is, a datacenter IP in
**AS16509**. Same machine, same IP, same sitting, for both families of endpoints.
Where a browser is mentioned, it was a **real** headless Chromium driven by
Playwright, not an HTTP client wearing a costume.

## Consumer job boards

### Indeed

`indeed.com` and `cl.indeed.com` returned **HTTP 403**, with the response header
`cf-mitigated: challenge` and a **Cloudflare Turnstile** widget in the body.

What matters is what was already controlled for when that happened. This was not
`requests`: it was real headless Chromium, which sends a correct browser TLS
fingerprint, plus

- a realistic Chrome User-Agent,
- `locale=es-CL`,
- `timezone=America/Santiago`,
- `navigator.webdriver` patched out.

With all of that in order, the answer was still 403. In other words: **the browser
fingerprint was fine, and the IP was the disqualifying variable.**

`rss.indeed.com` also returned **403**.

### Get on Board

This one is more interesting because it does not fail immediately. A single request
looks perfectly fine. The degradation shows up with volume:

| Rate | Result |
|------|--------|
| ~2 requests/second, 25 sequential | **17 of 25** returned 403 |
| 1 request every 5 seconds | **3 of 5** still failed |

The 403s carried `server: cloudflare` and `cf-cache-status: DYNAMIC`, but **no**
`cf-mitigated` header. Cutting the rate to a fifth did not fix it, which suggests
the score does not depend on pace alone.

### LinkedIn

- **Voyager** API: **403**.
- Logged-out guest jobs endpoint: **25 of 25** requests succeeded at 1/second.

So within one domain there is an endpoint that rejects the datacenter IP and one
that does not.

## Public ATS job-board APIs

From the same IP in the same minute, **every** public ATS job-board JSON API
returned **200**:

| Vendor | Endpoint |
|--------|----------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{co}/jobs` |
| Lever | `api.lever.co/v0/postings/{co}` |
| Ashby | posting-api |
| SmartRecruiters | public postings API |
| Breezy | public postings API |
| BambooHR | public postings API |
| Personio | XML feed |
| Workday | **400** on GET; **200** on POST with a JSON body |

Workday is not a block: that endpoint simply expects a POST with a JSON body and
answers 400 to a GET.

### Stress test

To rule out that the 200s were luck or leniency at low volume:

| Test | Result |
|------|--------|
| 40 rapid-fire Greenhouse requests, zero delay | **40/40 HTTP 200** |
| 30 rapid Lever requests | **30/30 HTTP 200** |

And to rule out the User-Agent as the relevant variable, the same calls were
repeated against Greenhouse, Lever and Ashby under three identities:

- `python-requests/2.32.3` → 200
- `curl/8.5.0` → 200
- an **empty** User-Agent → 200

You do not even have to lie about who you are.

## Why the split is this clean

The conclusion here is factual, not ideological.

Consumer job boards sit behind **CDN bot management**, which scores datacenter ASNs
down. The traffic they expect is a person with a browser on a residential
connection, and anything far from that pays a price — even when the browser is
genuine, as the real-Chromium run demonstrates.

ATS job-board APIs are **the same endpoints each vendor's own embeddable careers
widget calls from an ordinary visitor's browser**. They are designed to be consumed
publicly, without a session, from anywhere. There is nothing to trip.

### What this means for JobBot users

- **Browser-based portal work** (`indeed`, `linkedin`, `getonboard`) belongs on
  **your own machine, on your own residential connection**. That is exactly where
  JobBot puts it: local sessions under `browser-data/`, with the human in charge
  whenever a challenge appears.
- **ATS-direct discovery** can run anywhere: a server, a container, a cron job. It
  needs no browser and no session.

If your architecture assumes the opposite — scraping consumer portals from the
cloud — you will spend your engineering budget fighting a CDN, and the CDN will
keep winning.

## Context: this is measured in the literature

This is not one afternoon's anecdote. Gundelach, Muhlhauser and Herrmann (2026),
*"Detecting bot detection: prevalence, techniques, and implications for web
measurement research"*, [arXiv:2606.14525](https://arxiv.org/abs/2606.14525)
([DOI 10.48550/arXiv.2606.14525](https://doi.org/10.48550/arXiv.2606.14525)),
visited 10,000 sites with 40,000 Playwright page visits from a datacenter IP:

- sites fronted by **Cloudflare blocked 37.0 %** of visits;
- sites fronted by **Akamai, 26.4 %**;
- and **83 % of papers** published at top venues **never mention** that bot
  detection may have affected their results.

That last number is the uncomfortable one: a lot of web-measurement research
reports findings gathered from datacenter IPs without accounting for the fact that
a large share of the sample never really answered.

## A note on ethics and manners

An endpoint answering 200 is not authorization.

None of these ATS vendors documents a read rate limit. That is a **reason for
restraint, not a permission**. No published limit means you do not know the limit,
not that there is none.

Concrete recommendations, which is what JobBot does:

- **150–300 ms spacing** between requests. It is free and it removes the
  pathological case.
- A **real, identifying User-Agent** with a way to reach you. If you are bothering
  someone, let them ask you to stop.
- **Back off** on `429` and on any `5xx`. A 429 is an instruction, not a transient
  error to retry through.
- Small, sequential volumes. JobBot is not a crawler and should not become one.

---

*Every number in this post was measured on 2026-09-24 from an AWS IP in `us-west-2`
(AS16509). A measurement from another network, another ASN or another date may
differ; that is exactly the point.*

*Versión en español: [Qué sitios de empleo te bloquean desde una IP de datacenter
(medido)](2026-09-24-bloqueos-ip-datacenter.md).*
