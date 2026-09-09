# RespectASO MCP

Use the installed tool schema as authority; releases and account capabilities change. This is a
workflow, not a claim that every host has the same license or 24 tools forever.

## Connection and prerequisites

Discover native MCP tools first. RespectASO on macOS also ships a stdio MCP executable at
`/Applications/RespectASO.app/Contents/MacOS/respectaso-mcp`. An app web UI on port 8000 is not
an HTTP MCP endpoint. Do not add guessed `/mcp` routes or silently change user-wide configuration.
A protocol initialization and `ping` prove connectivity only. Call `get_pro_status` next. Record
`no_license`, inactive status or missing AI configuration as a capability gap; never bypass a gate.

A baseline MCP check without an active license returns `ping=ok`, no installed license, INACTIVE, and no AI provider.
`list_tracked_apps` and `get_popularity_source` returned an embedded `error: no_license` while outer
MCP `isError` was false. Inspect BOTH the transport envelope and the returned content. No successful
keyword research was obtained through MCP in that check. See the app's saved MCP evidence, not this
historical example, for current access.

## Useful tool groups

| Goal | Tools observed in the installed schema | Important boundary |
|---|---|---|
| Check access and identity | `ping`, `get_pro_status`, `list_tracked_apps`, `get_app_id_from_name` | Verify the returned store ID/bundle, not a name substring |
| Inspect a query | `search_keyword`, `get_saved_keywords`, `get_popularity_source` | `search_keyword`: exact country and `save=false` for read-only work |
| Apple demand context | `get_top_search_terms`, `get_impression_share` | Preserve week/genre; own ad share is not total organic demand |
| Metadata assistance | `validate_metadata`, `extract_keywords`, `discover_combinations` | Validation and combinations are tools' heuristics, not proof of Apple indexing |
| Coverage scan | `evaluate_coverage`, `get_coverage_results` | Save scan ID; poll boundedly; partial results stay partial |
| Market comparison | `opportunity_search`, `get_opportunity_results` | A scan starts background work; compare like sources and dates |
| AI research | `research_keyword`, `analyze_competitor`, `simulate_metadata` | Needs configured AI; may incur provider usage; generated ideas need evidence |
| Background jobs | `list_sessions`, `get_session_result`, `cancel_session` | Check tool/session kind; do not cancel somebody else's work |
| Change scoring source | `set_popularity_source` | Mutates app-wide settings and recomputes scores; not a read |

## Data contract

Retain the raw result alongside its interpretation. Every query observation needs:
`app_id/bundle_id`, exact `keyword`, `country`, `observed_at`, `data_date/week`, `provider`,
`query_status`, `rank_kind`, `depth`, `popularity_detail`, selected source and fallback flag.
Never join by translated text or copy an English difficulty score to a native keyword.

Apple popularity is a relative indicator, not monthly searches. The low end can be censored at 5;
it cannot reliably distinguish all low-demand queries. An internal fallback remains an estimate
even when Apple is the selected source. `get_top_search_terms` exposes weekly Apple data; always
record the exact week and category, not the all-time maximum. Impression-share results describe
our served ads and can suppress small cells; empty does not establish zero searches.

For a metadata candidate: validate product relevance, research the exact native query, preserve
source details, inspect competitors, compare with live metadata, then define a measurable test.
For a blocked MCP: record the error, use clearly labelled historical/public discovery evidence if
useful, and leave live demand unknown. Never relabel a legacy HTTP report as new MCP research.

## Verification

After access is available, verify one known app and three query cases: an Apple value, an internal
fallback and an unavailable result. A successful protocol handshake alone does not close this gate.
Use official distribution/release notes: https://github.com/respectlytics/respectaso/releases
and the installed tool schemas. Do not assume an older free-version README describes Pro features.
