# StegoShield — Security Review

This is a self-review performed against the project's own threat model:
**an anonymous user submits untrusted image files (and text) to a
Flask web application that decodes, transforms, and analyzes them.**
It is written honestly, including residual/unfixed risk. StegoShield is
an academic/portfolio project, not an audited production system —
**it is not claimed to be "100% secure."**

## Audit history

This document has gone through three passes. The first pass (initial
build) self-reviewed the code as written. A second, independent,
adversarial pass — using a fresh reviewer (a subagent with no
authorship bias) specifically hunting for XSS/injection paths, ML data
leakage, and claims in this document that didn't hold up under direct
testing — found and fixed 4 real issues (#10, #16, #17, #18 below),
including one genuine High-severity finding (#10) that contradicted
what an earlier version of this document claimed. That earlier,
incorrect claim is left visible in the diff/history rather than
quietly rewritten, because an audit trail that only ever finds
"everything was already fine" is not a credible one.

A third pass — live, dynamic testing (direct HTTP requests, timing
measurements, and Playwright browser automation with console-error
monitoring, as opposed to the second pass's static code reading) —
found two further real issues the static review missed entirely: a
resource-exhaustion ordering bug (#20, found via direct timing
measurement) and a CSP configuration bug that silently broke a UI
feature (#19, found via a live browser console error during automated
testing). A dependency scan (`pip-audit`) separately found and fixed
one known CVE in a pinned dependency (#21).

## Scope

Reviewed: `app/` (Flask backend, routes, security, services), the
steganography engine (`app/steganography/`), the steganalysis pipeline
(`app/steganalysis/`), and the frontend JavaScript that consumes the
API (`frontend/static/js/`). Not in scope: infrastructure/deployment
hardening (TLS termination, WAF, container hardening), which is
environment-specific and outside a portfolio project's control.

## Findings

| # | Finding | Severity | Status | Mitigation |
|---|---|---|---|---|
| 1 | Path traversal via uploaded filename | Low | **Mitigated** | Uploaded filenames are used only to read the extension string for the allow-list check (`validators.validate_extension`). No filesystem path is ever built from a client-supplied filename anywhere in the codebase — the app never persists uploads to disk at all (see #6). |
| 2 | Unrestricted file upload (arbitrary file type / disguised executable) | High | **Mitigated** | Three independent layers: (a) extension allow-list, (b) `python-magic` content-signature sniffing of the *actual* bytes (a renamed `.exe` is rejected even with a `.png` name), (c) Pillow `Image.verify()` + a full decode, which rejects anything that isn't a genuinely well-formed image. See `app/security/validators.py`. |
| 3 | Decompression-bomb / resource-exhaustion via huge or absurdly-dimensioned image | Medium | **Mitigated** | `Image.MAX_IMAGE_PIXELS` ceiling, an explicit `MAX_IMAGE_DIMENSION` check (default 6000px/side), and `MAX_CONTENT_LENGTH` enforced at both the WSGI layer (Flask `413`) and again in application code for defense in depth. |
| 4 | Arbitrary code execution via uploaded content | Critical | **Mitigated** | Uploaded bytes are only ever passed to `PIL.Image.open` / NumPy — never to `eval`, `exec`, `pickle.loads`, `subprocess`, or any shell. There is no code path where uploaded content is interpreted as code. |
| 5 | Command injection | Critical | **Mitigated (by design)** | The application never constructs or executes a shell command from any request input — no `subprocess`, `os.system`, or shell string formatting exists in `app/` at all. |
| 6 | Unsafe temporary-file handling / leftover uploaded data on disk | Medium | **Mitigated (stronger than typical)** | The live encode/decode/steganalysis/image-analysis pipelines never write uploaded bytes to disk — they operate end-to-end on in-memory `BytesIO` objects and NumPy arrays. There is therefore no temp-file cleanup risk for the current feature set. `app/security/file_handler.py` still provides a hardened, tested temp-file context manager (random non-guessable names, `0600` permissions, guaranteed cleanup via `try/finally` even on exception — see `tests/test_file_handling.py`) for any future feature that does need scratch files. |
| 7 | Information leakage via stack traces / internal paths in error responses | High | **Mitigated** | A global Flask error handler (`app/__init__.py::_register_error_handlers`) catches every exception, logs full details server-side only, and returns a generic, stable JSON error to the client. Domain exceptions are mapped to safe messages via `app/utils/errors.py`. Verified in `tests/test_security.py::test_response_never_leaks_stack_trace`. |
| 8 | Secret / credential exposure in the repository | Medium | **Mitigated** | No secrets are committed. `.env` is git-ignored; `.env.example` ships with placeholder values only. `SECRET_KEY` defaults to an obviously-fake development value and **must** be overridden via environment variable in any real deployment — documented in `.env.example` and the README. |
| 9 | Debug mode / interactive debugger exposed in production | High | **Residual risk — operator responsibility** | `Config.DEBUG` defaults to `False` (`ProductionConfig`); debug mode (and Flask's interactive debugger/reloader) is only enabled when `FLASK_ENV=development` is explicitly set. The README instructs running with a production WSGI server (gunicorn), not `python run.py`, for any real deployment. |
| 10 | Reflected XSS via a crafted upload filename echoed into an API error message | High | **Found in second-pass audit — fixed** | `validate_extension()` echoed the client-supplied filename's "extension" (the substring after the final `.`) verbatim into the `invalid_image` error message, and the frontend's `showAlert()` rendered every error message via `innerHTML`. A filename such as `evil.<img src=x onerror=alert(1)>` reached the DOM unescaped. Confirmed exploitable with a Flask test-client request (see `tests/test_security.py::test_crafted_filename_not_reflected_in_error_message`, added as a regression test). **Fixed at two independent layers**: (1) `validate_extension` now only echoes the extension back when it matches a short alphanumeric pattern (`app/security/validators.py`), so arbitrary attacker strings are never reflected; (2) `showAlert()` (`frontend/static/js/app.js`) now builds the alert via `document.createElement` + `textContent` instead of `innerHTML`-with-interpolation, so *no* error message — from this or any future code path — can be parsed as markup. Jinja2 auto-escaping still covers all server-rendered templates; the decoded secret message is assigned via `textarea.value` (`decode.js`), which never parses HTML; every other `innerHTML` use in `frontend/static/js/` was individually re-audited and confirmed to render only fixed-vocabulary, server-computed values (feature names, numeric scores, model names, timestamps) — never a raw user-supplied string. |
| 11 | CSRF | Low / Not directly applicable | **Documented** | The API has no authentication or session cookies, so there is no ambient authority for a cross-site request to ride on — classic CSRF does not apply to the current design. If authentication is added in the future, CSRF tokens must be added to all state-changing endpoints at that time. |
| 12 | Denial of service via request flooding | Medium | **Partially mitigated** | Flask-Limiter rate-limits upload-heavy endpoints (`RATE_LIMIT_UPLOAD`, default 10/minute/IP) and applies a default limit elsewhere. **Residual risk:** the limiter's default in-memory storage is per-process and resets on restart — it is not suitable for a multi-worker/multi-instance production deployment without a shared backend (Redis), which is documented but not implemented here (out of scope for a single-instance portfolio deployment). |
| 13 | JPEG re-encoding silently corrupting a payload | Low (correctness, not strictly security) | **Mitigated** | Encoding is refused outright for non-lossless formats (`validate_lossless_for_encoding`) rather than silently producing a stego image that would fail to decode later. |
| 14 | Sensitive data in logs | Medium | **Mitigated** | The structured logger (`app/utils/logging_config.py`) only ever receives metadata (image dimensions, byte counts, timings, prediction labels) via `extra=`. No route ever logs the secret message text or raw image bytes. Verified by code inspection of every `logger.info(...)` call site. |
| 15 | Server header / framework fingerprinting | Low | **Residual risk** | The Flask development server exposes a `Werkzeug/...` `Server` response header. This is expected for `python run.py` (development use only); a production deployment behind gunicorn/nginx should strip or replace this header at the reverse-proxy layer — a standard operational step outside this codebase's scope. |
| 16 | Dashboard "Recent Analysis" panel inconsistent across a multi-worker deployment | Low (functional, not security) | **Documented** | `app/services/activity_log.py` is a process-local in-memory deque. Under `gunicorn --workers 2` (as this project's own README suggests for production), a request handled by one worker won't appear in a subsequent page load routed to a different worker. This never gates a security decision — it's a cosmetic dashboard limitation, the same class of issue as the rate limiter's documented per-process storage (#12) — but is now explicitly called out in code (`activity_log.py` module docstring) rather than left implicit. |
| 17 | Every upload was fully decoded by Pillow up to three times per request | Low (performance, not security) | **Fixed** | `app/security/validators.py::validate_and_decode_image` now decodes the image once and attaches the resulting RGB NumPy array to the returned `ValidatedUpload.rgb_array`; all four services (`encode_service.py`, `decode_service.py`, `steganalysis_service.py`, `image_analysis_service.py`) were updated to reuse it instead of independently re-decoding via `app.utils.image_io.bytes_to_rgb_array`. Verified by the full test suite and a manual encode→decode round trip after the change. |
| 18 | Ordinary validation failures logged as `ERROR`-level "unhandled exceptions" with full stack traces | Low (log hygiene, not a vulnerability) | **Fixed** | Domain validation errors (bad upload, message too large, no payload found, checksum mismatch) previously fell through to the catch-all `@app.errorhandler(Exception)`, which logs via `logger.exception(...)` — burying genuine unexpected errors in noise from routine, expected 400/404/422 responses. A dedicated `@app.errorhandler(SteganographyError)` (`app/__init__.py`) now handles these explicitly and logs them once at `INFO` with no stack trace. Regression test: `tests/test_security.py::test_domain_validation_errors_logged_at_info_not_error`. |
| 19 | CSP `img-src` directive blocked local file-preview thumbnails (`blob:` URLs) | Low (functional, not a vulnerability) | **Fixed** | Found via live browser testing (Playwright), not the static audit: `URL.createObjectURL(file)` — used by the Encode/Decode/Steganalysis/Image-Analysis pages to show a local preview before upload — produces a `blob:` URL, but the CSP's `img-src` directive only allowed `'self' data:`. Every preview thumbnail was silently broken. Fixed by adding `blob:` to `img-src` in `app/__init__.py`. Regression test: `tests/test_security.py::test_csp_img_src_allows_blob_for_local_previews`. Re-verified live via Playwright on all 4 affected pages after the fix (no console errors, thumbnails render with a nonzero decoded width). |
| 20 | Resource-exhaustion ordering bug: oversized images were fully decoded before being rejected | Medium (self-discovered, not flagged by the second-pass audit) | **Fixed** | `validate_and_decode_image` checked image dimensions *after* a full Pillow decode (`.verify()` + `.load()`), so a small, highly-compressible PNG declaring huge pixel dimensions ("decompression bomb") forced expensive decode work before rejection. Measured directly: a 7000×7000 flat-color PNG (0.15 MB file) took ~0.94s to reject before the fix. Fixed by checking dimensions from a cheap header-only `Image.open().size` probe first; rejection now takes ~0.007s. Regression test (`tests/test_security.py::TestDimensionLimits::test_oversized_dimensions_rejected_before_full_decode`) monkeypatches `Image.Image.load` with a spy to prove the full decode path is never reached. |
| 21 | Known CVE in a pinned dependency (`python-dotenv==1.0.1`, PYSEC-2026-2270) | Medium | **Fixed** | Found via `pip-audit -r requirements.txt`. Upgraded to `python-dotenv==1.2.2` (the fixed release) in `requirements.txt` and the project's virtual environment. Re-ran `pip-audit` afterward and confirmed "No known vulnerabilities found" across all pinned dependencies. |

## What was NOT found

No SQL injection surface exists (the project uses no database). No
deserialization of untrusted data (`pickle`, `yaml.load`, etc.) occurs
anywhere in the request path — the only deserialization is `joblib.load`
of the **project's own** locally-trained model artifact at startup, not
of any request input.

## Summary

The highest-severity risks for an image-processing web application —
arbitrary file upload, code execution via untrusted input, and stack
trace / path disclosure — are directly and verifiably mitigated, with
tests covering the security-relevant behavior (`tests/test_security.py`,
`tests/test_file_handling.py`). The remaining items are either standard
deployment-environment responsibilities (TLS, reverse proxy, WSGI
server, distributed rate-limit backend) that are explicitly documented
rather than silently ignored, or low-severity items with no practical
exploitation path in the current design.
