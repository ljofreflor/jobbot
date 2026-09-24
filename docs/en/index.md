---
title: JobBot in English
description: >-
  JobBot is a local-first CLI for job hunting. It runs entirely on your machine,
  never submits an application for you and never invents facts about you.
---

# JobBot, in English

**JobBot is a command-line tool that keeps your CV as structured data, discovers
job postings, scores them against your real profile and assembles the application
package.** You press submit. Always.

This site is written in Spanish, because the author writes in Spanish and the tool
targets the Chilean and wider LATAM market. This page and the technical
measurement posts are the English surface.

## Install in three commands

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
```

Then edit `data/profile.yaml` with your own data and check it:

```bash
uv run jobbot profile validate
uv run jobbot cv build
```

## What makes it different

- **Runs entirely locally.** Python, SQLite and a local Playwright browser. No
  remote service, no account, no telemetry.
- **Never submits an application for you.** The loop is human-in-the-loop: JobBot
  prepares the package and plans the form fill; you review and send.
- **Never invents facts about you.** `data/profile.yaml` is the single source of
  professional truth. A job-adapted CV reorders and prioritises what is already
  there.
- **No CAPTCHA bypass.** No solving challenges, no 2FA workarounds, no anti-bot
  evasion. When a portal asks, it hands you the keyboard.
- **Your data never leaves your machine.** Profile, output, browser sessions and
  the SQLite database are gitignored, and a pre-commit hook blocks them.

## A full loop, in commands that exist

```bash
uv run jobbot getonboard search "data scientist" --limit 20
uv run jobbot jobs shortlist
uv run jobbot jobs match J0001
uv run jobbot cv build --job J0001
uv run jobbot application prepare J0001
uv run jobbot application apply J0001        # plan only; you submit
```

## Read next

- [Which job sites block you from a datacenter IP (measured)](../blog/posts/2026-09-24-datacenter-ip-blocking.md)
  — 403s, headers and counts from an AWS IP, plus why ATS APIs behave differently.
- [Prior art](../prior-art.md) — other open-source projects in this space.
- [Instalación](../instalacion.md) and [Comandos](../comandos.md) — the full docs,
  in Spanish.
