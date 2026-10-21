# Cross-repository dependency-chain CI

The stargazing packages form this dependency graph:

```text
stargazing-core ───────────────> mcp-stargazing
        └──> stargazing-place-finder ──> mcp-stargazing
```

Every repository calls the reusable workflow in
`StarGazer1995/mcp-stargazing/.github/workflows/dependency-chain-reusable.yml`.
The MCP repository is the final consumer, so it owns the orchestration; production
packages continue to resolve dependencies from PyPI.

## What runs

| Changed repository | Downstream checks |
|---|---|
| `stargazing-core` | SPF Python suite and MCP Python suite |
| `stargazing-place-finder` | MCP Python suite |
| `mcp-stargazing` | MCP Python suite |

The workflow builds real wheels for all three repositories, then force-installs the
local core and SPF wheels into the downstream test environment. This is deliberately
stricter than `uv sync --frozen`: it verifies package layout and namespace behavior
as well as source-level compatibility.

## Baseline and candidate

Every affected downstream runs twice:

| Job | Changed repository | Other repositories |
|---|---|---|
| `baseline` | Pull request base SHA | Their `main` branches |
| `candidate` | Pull request head SHA | Their `main` branches |

The result gate compares failed JUnit test IDs:

- Baseline passes and candidate fails: block.
- Candidate adds a failing test not present in the baseline: block.
- Candidate has the same known failures as the baseline: allowed on PR and merge
  queue gates, reported as `KNOWN_BASELINE`.
- Main-branch and manual runs use the strict gate, so any failure blocks.
- Both sides fail without comparable test IDs: block because attribution is not
  trustworthy.

The job summary records both refs, failed tests, and the final decision. Test logs
and JUnit reports are retained as workflow artifacts for seven days.

Pushes to `main` run the strict check from each repository's auto-tag workflow.
Tag-triggered PyPI and Docker jobs also depend on the same strict check, so a
manual tag cannot bypass a failing dependency chain.

## Coordinated changes

If one change spans repositories before the upstream change has merged, run the
caller workflow manually and pass a JSON override:

```json
{
  "stargazing-core": "refs/pull/123/head",
  "stargazing-place-finder": "refs/pull/456/head"
}
```

The changed repository still uses `candidate_ref`; overrides apply only to the
other repositories. This supports validating a coordinated change set without
weakening the normal PR gate.

## Rollout

1. Merge the MCP change first so the reusable workflow exists on `main`.
2. Merge the core and SPF caller workflows.
3. Mark the `Dependency Chain / Evaluate dependency-chain regression` check as
   required on each repository's default branch.
4. Keep native per-repository CI required as well. The dependency chain focuses on
   consumer compatibility and does not replace frontend, Docker, lint, or coverage
   checks owned by each repository.

The repositories are public, so dependency checkouts use anonymous HTTPS access.
If any repository becomes private, provide a read-only GitHub App token, but do not
expose that token to untrusted fork pull requests.
