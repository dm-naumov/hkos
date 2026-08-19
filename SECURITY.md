# Security Policy

## Reporting a vulnerability

Please report security issues privately to **hkos_dmitry@proton.me**
(preferred: encrypt with the key published in the GitHub profile). Do not open
a public issue for anything that could be exploited.

Include, if possible:

- the affected version(s);
- a minimal reproduction (corpus shape, API calls);
- the impact (data loss, integrity violation, crash, ...).

## What HKOS protects

HKOS stores engineering knowledge as plain JSON files. The security-relevant
properties of the system are:

1. **SSOT integrity** — the repository is the only source of truth; index /
   snapshot / manifest / cache corruption is detectable and rebuildable.
2. **Crash safety** — all writes are atomic (tmp + rename); a `kill -9`
   mid-write leaves zero partial records.
3. **Write-path discipline** — knowledge is written only through the
   Librarian; the Hermes integration layer enforces command permissions
   (READ/WRITE/ADMIN), confirmation for ADMIN commands, and an append-only
   audit log.
4. **Determinism** — no LLM or external service is consulted during write,
   classify, index, or retrieve; there is no prompt-injection surface in the
   memory pipeline itself.

## Out of scope

- LLM prompt injection against agents *using* HKOS (mitigate in the agent
  layer; HKOS treats knowledge as data).
- Multi-tenant/multi-user authorization (HKOS is a single-owner library;
  filesystem permissions apply).
