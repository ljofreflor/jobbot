---
template: home.html
title: Jobbot — your next step, with intelligence
description: >-
  Local CLI for job hunting: find openings, prepare applications, and you press
  submit. Human + technology, on your machine.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## People · opportunities · technology

Three things Jobbot actually does. No invented product.

<ul class="jb-benefits">
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    </div>
    <strong>Find opportunities</strong>
    <span>Discover openings that fit your real profile — not an invented CV.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/><path d="M9 21l1.5-1.5L13 21"/></svg>
    </div>
    <strong>Apply more easily</strong>
    <span>Assemble the package, open the form, and leave sending to you.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M20 19H3"/></svg>
    </div>
    <strong>Move forward with confidence</strong>
    <span>Matching against your profile, shortlist and evidence — no account, no telemetry.</span>
  </li>
</ul>

<p class="jb-pillars">More opportunities. A better tomorrow.</p>

</section>

<section class="jb-section" markdown="1">

## A full loop, in commands that exist

Discover, score, build the CV, prepare the application. You press submit.

```bash
uv run jobbot getonboard search "data scientist" --limit 20
uv run jobbot jobs match J0001
uv run jobbot cv build --job J0001
uv run jobbot application apply J0001        # plan only; you submit
```

</section>

<section class="jb-section" markdown="1">

## What Jobbot will not do

Product rules, not slogans.

<ul class="jb-principles">
  <li><strong>Never submits for you</strong> Human-in-the-loop: it prepares the package and opens the form. Sending is yours.</li>
  <li><strong>Never invents facts about you</strong> <code>data/profile.yaml</code> is the only source of professional truth.</li>
  <li><strong>Never leaves your disk</strong> Profile, SQLite, browser sessions and <code>output/</code> are gitignored.</li>
  <li><strong>No CAPTCHA bypass</strong> When a portal challenges you, it hands you the keyboard.</li>
</ul>

</section>

<section class="jb-section jb-section--measure" markdown="1">

## Measured, not guessed

Which job sites answer from a datacenter IP, and which do not.

[Read the measurement](../blog/posts/2026-09-24-datacenter-ip-blocking.md){ .jb-btn .jb-btn--primary }
[Sitio en español](../index.md){ .jb-btn .jb-btn--ghost }

</section>
