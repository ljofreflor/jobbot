---
template: home.html
title: JobBot — job search on your machine
description: >-
  Local-first CLI for job hunting. Runs entirely on your machine, never submits
  an application for you and never invents facts about you.
hide:
  - navigation
  - toc
---

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

## What JobBot will not do

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
