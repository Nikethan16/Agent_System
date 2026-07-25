---
name: understand-first
description: Understand a shared repo, codebase, app, or URL by reading the ACTUAL source before describing or changing it — and never invent what you couldn't read. Use when asked to understand, summarize, explain, review, or analyze a repository, project, app, or link.
keywords: [understand, summarize, summarise, explain, describe, analyze, analyse, review, repo, repository, codebase, code base, github, gitlab, bitbucket, url, link, readme, project, application, app, what is, walk through, go through, get a sense]
agents: [repo-engineer, research, coder, fast-coder, doc, general]
---

# Understand the source before you describe or change it

When someone shares a repository, codebase, app, or URL and asks what it is (or to review / summarize / change it), your FIRST job is to read the ACTUAL thing. Never work from the name, the URL, or a guess.

## Rules — non-negotiable
1. **Fetch the real source first.** Clone the repo (or read its README via the GitHub tools, or `web_fetch` the URL) and READ it. Understand it at a **product level first** — what it does, who it's for, its main features — from the README/docs, before touching code.
2. **Never describe what you haven't read.** Do NOT invent, guess, or pattern-match a description from the project's name. If you have not actually read the source, you do not know what it is — and you must not pretend to.
3. **If you can't access it, STOP and say so — plainly.** "I couldn't reach / clone `<X>` because `<reason>`" is the correct, honest answer. A fabricated summary is far worse than an honest failure: it actively misleads. Never fill the gap with plausible-sounding invention.
4. **Don't build or change anything yet.** When the ask is to *understand / summarize*, deliver the summary and stop. Wait for the user to say what to change or build next.

## How to read it
- **A git URL / repo** → clone it (or read it via the GitHub tools), then read: `README`, `docs/`, the manifest (`package.json` / `pyproject.toml` / `go.mod`), and the entry points. That tells you what it is and how it runs.
- **A plain URL** → `web_fetch` it and read the page.
- **An existing local codebase** → list the files and read the README + entry points before summarizing.

## Deliver
A brief, plain-language summary: what it is (1–2 sentences), who it's for, its main features, and how it works at a high level (CLI? web app? runs locally? sends email?). Ground every claim in what you actually read; if something is unclear or you didn't read it, say so — don't paper over gaps.

## The failure this prevents
Being handed `github.com/foo/bar`, never fetching it, and writing a confident description **invented from the name**. That is a hallucination and a serious error. Read first — or say you couldn't.
