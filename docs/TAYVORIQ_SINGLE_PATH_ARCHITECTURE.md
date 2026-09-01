# TAYVORIQ Single-Path Architecture

## Purpose

TAYVORIQ must have exactly one source of truth for a content request and exactly one production owner. Topics are request data, never workflow definitions.

## Repository ownership

### tayvoriq-control-plane
Owns orchestration only:
- trend intake and Telegram selection/approval
- immutable request contract and request_id
- queue/serialization and lifecycle state
- dispatch to shorts-agent-studio
- Control Center read model and incident visibility
- approval state and publish authorization

It must not render video, synthesize voice, generate visuals, or contain topic-specific production fallbacks.

### shorts-agent-studio
Owns production only:
- script and source-bound content generation
- voice, visuals, captions and 9:16 rendering
- bounded request-bound self-heal
- quality gates
- review artifact creation and Telegram review delivery
- approved publish package/upload execution

It must not select a new trend while processing an approved request.

## Canonical request lifecycle

SELECTED -> APPROVED -> DISPATCHED -> PRODUCING -> SELF_HEAL (optional) -> QUALITY -> REVIEW_READY -> APPROVED_FOR_PUBLISH -> PUBLISHED

The same request_id, topic, source set and approval binding must survive every transition.

## Non-negotiable guards

1. No hard-coded content topic in a production or recovery workflow.
2. No fallback to a previous topic. Missing request data fails closed.
3. Recovery may repair only the same request_id and checkpoint.
4. Only Control Plane may decide what request runs next.
5. Only Studio may perform media production.
6. One production workflow must be the canonical Studio entrypoint.
7. At most one generic request-bound recovery path may exist; prefer integrating it into production.
8. Quality gates may not be bypassed by recovery.
9. Control Center displays request lifecycle, not competing workflow internals.
10. Historical/topic/date/run-specific workflows are removed from active .github/workflows.

## Control Center presentation

Primary card fields:
- Topic
- request_id
- lifecycle stage
- production run id
- progress
- current bounded recovery attempt (if any)
- last concrete error
- review artifact / publish result

Primary stages shown to the user:
Selected -> Producing -> Quality -> Review Ready -> Published

Self-Heal is shown only as a temporary sub-state of Producing, never as a second production request.

## Current canary

The cleanup is validated with the existing LUMI-AI request `telegram-1965-trend-2`. Validation succeeds only when this exact request reaches REVIEW_READY without topic substitution or a duplicate production request.
