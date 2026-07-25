---
name: security-guidance
description: Write secure code by default — avoid injection, unsafe deserialization, XSS, XXE, weak crypto, and secret leaks. Use whenever building or editing code that handles user input, files, network requests, auth, or data parsing.
keywords: [security, secure, auth, login, password, credential, secret, token, api, endpoint, sql, query, database, upload, file, request, url, fetch, subprocess, shell, command, exec, eval, deserialize, pickle, yaml, xml, xss, html, template, crypto, encryption, ssl, tls, cookie, session, user input, sanitize, validate]
agents: [coder, fast-coder, frontend, data-analyst, repo-engineer]
---

# Write secure code by default

This is **build-time guidance** (write it safe the first time) — separate from the runtime policy gate that blocks dangerous *actions*. When a task touches user input, files, the network, auth, or parsing, apply the rules below and briefly note in your report which ones were relevant.

Golden rule: **treat all external input as hostile** — request params, form fields, uploaded files, filenames, headers, env, and any fetched/parsed content. Validate and encode at the boundary.

## Command / code injection
- Never build a shell command by string-concatenating input. Avoid `shell=True` (Python `subprocess`), `os.system`, Node `child_process.exec/execSync`, Go `exec.Command("sh"/"bash", "-c", …)`. Pass args as a **list/array** to the exec API instead.
- Never `eval()`, `new Function()`, `pickle`-style code paths, or `exec()` on anything derived from input.
- Parameterize every SQL query (bound placeholders) — never format user values into the query string. Same for NoSQL query objects.

## Unsafe deserialization (arbitrary code execution)
- Do **not** load untrusted data with: `pickle`/`cPickle`/`cloudpickle`/`dill`, `marshal`, `shelve`, `yaml.load` without `SafeLoader` (use `yaml.safe_load`), `torch.load` without `weights_only=True`, `joblib.load`, `pandas.read_pickle`, or `numpy.load(allow_pickle=True)`.
- Prefer JSON or another data-only format for anything crossing a trust boundary.

## Web / XSS / templating
- Never write untrusted input into the DOM via `innerHTML`/`outerHTML`/`document.write`/`insertAdjacentHTML`, or React `dangerouslySetInnerHTML`. Set text via `textContent`, or escape/encode for the exact context (HTML, attribute, JS, URL).
- Enable framework auto-escaping; don't disable it. Don't load remote `<script src>` without Subresource Integrity (`integrity=`).
- Set security headers where relevant (CSP, `X-Content-Type-Options`), and cookies `HttpOnly` + `Secure` + `SameSite`.

## XML / XXE
- Parse XML with a hardened parser (`defusedxml` in Python) — the stdlib ElementTree/SAX parsers are vulnerable to XXE and billion-laughs on untrusted XML.

## Crypto & transport
- Never disable TLS verification (`verify=False`, `rejectUnauthorized:false`) outside a throwaway test.
- Use authenticated modes (AES-GCM), never ECB; never fixed/empty IVs or `crypto.createCipher` (no IV). Use a vetted library, not hand-rolled crypto. Hash passwords with bcrypt/argon2/scrypt, never plain SHA/MD5.

## Secrets & data
- Never hardcode API keys, tokens, or passwords — read from env/secret store. Never log secrets, tokens, or full PII.
- Validate file paths against a base dir before joining (path-traversal / `..`); validate upload type and size.
- Enforce authorization on every object access (guard against IDOR — "can THIS user touch THIS record?"), not just authentication.

## Before you finish
Re-scan your diff for the patterns above. If a task legitimately needs a flagged construct, isolate it, justify it in a comment, and call it out in your report — don't leave it silent.
