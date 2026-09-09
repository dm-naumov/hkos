# MCP observation write path

The MCP `save` tool records agent output as a `NEW` observation by default.
Saving and trust promotion are separate decisions: ordinary retrieval remains
`CANONICAL`-only, while `include_history=true` can inspect indexed observations.

`canonicalize=true` remains an explicit elevated compatibility action for this
stage. Removing the implicit `NEW -> VERIFIED -> CANONICAL` transition is KI-004
and is intentionally out of scope here.

## Contract

- omitted `canonicalize` -> `NEW`;
- `canonicalize=false` -> `NEW`;
- `canonicalize=true` -> explicit promotion (compatibility behavior);
- every saved item is indexed; eligibility, not index omission, controls ordinary retrieval.
