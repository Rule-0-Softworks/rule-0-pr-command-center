# Required-check semantics probe

## Scope

Effective base-branch rules, legacy branch protection, merge queue, context names, and app identity.

## Evidence matrix

| Case | Endpoint/query | HTTP/result | Required context | App identity | Merge queue | Reliable |
|---|---|---:|---|---|---|---|
| Legacy branch protection | `BranchProtection` GraphQL query | Not run: credential unavailable | Unknown | Unknown | Unknown | No |
| Repository ruleset | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | Not run: credential unavailable | Unknown | Unknown | Unknown | No |
| Organization ruleset | `GET /repos/{owner}/{repo}/rulesets?includes_parents=true` | Not run: credential unavailable | Unknown | Unknown | Unknown | No |
| Merge queue | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | Not run: credential unavailable | Unknown | Unknown | Unknown | No |
| Unprotected branch | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | Not run: credential unavailable | Unknown | Unknown | Unknown | No |

No human-managed credential was available for this run, so no GitHub request was made. The sanitized fixtures retain the contract-shaped field names needed by the read model but are not claimed as live-probe evidence.

## Reconciliation rule

1. Use effective branch rules as the primary source.
2. Union enabled required-status-check rules that apply to the exact base branch.
3. Match by exact case-sensitive context name.
4. When an integration ID is present, require the same CheckRun app database ID.
5. Never assign an integration identity to a legacy StatusContext.
6. Mark missing, permission-denied, ambiguous, or incomplete evidence as unknown.
7. Record merge-queue requirements independently; do not claim the PR head itself satisfies merge-group checks.

## Gate result

FAIL: no credential was available to read effective rules. The application keeps required-check state unknown with diagnostic code `required_checks.evidence_unavailable` until a future read-only probe returns identities that map unambiguously.
