STORY KEY: e06s02
TITLE:     Apply workspace privacy rules to discovery
TYPE:      Story
PARENT:    e06
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Directory discovery can reveal protected names and sizes even when direct content reads are denied.

### 2. Value statement [reviewed]

Users can let the model explore ordinary project structure without disclosing protected entries.

### 3. Actors and permissions [reviewed]

Users own ignore policy; the model requests listings but cannot weaken built-ins or `.orbitrelayignore` denies.

### 4. Trigger and preconditions [reviewed]

e06s01 supplies the shared classifier; workspace and symlink confinement remain mandatory.

### 5. Main flow and business logic [reviewed]

Load rule metadata without protected file content, apply the approved catalog/precedence, reveal only entries covered by a pre-run exact-file or subtree exception, filter all other protected entries, and return one aggregate omitted count.

### 6. Alternative flows and exceptions [reviewed]

Malformed or unreadable policy fails closed for affected paths; ordinary dotfiles are not denied solely because they are hidden.

### 7. Interface elements [reviewed]

`get_files_info` keeps ordinary and explicitly authorized entries and adds an omitted-count field or line; unauthorized protected names and sizes are absent.

### 8. Domain model [reviewed]

The conservative built-in catalog, effective `.gitignore` matches/negations, deny-only `.orbitrelayignore` matches, ordinary dotfiles, run exceptions, and absolute denies form the exact precedence table in the aggregate plan.

### 9. Integrations and boundaries [reviewed]

Touches both read tools, path safety, tool schemas/results, and workspace fixtures.

### 10. Background processes [reviewed]

None; rules are evaluated within the run.

### 11. Notifications [reviewed]

The aggregate omitted count signals filtering without disclosing which entries matched.

### 12. Audit and logging [reviewed]

Events may record the count and policy outcome, never omitted names or sizes.

### 13. Solution variabilities [reviewed]

Use `pathspec` [OK] for Git-compatible ignore semantics; Git negation changes only Git-derived sensitivity, while `.orbitrelayignore` remains deny-only and rejects negation.

### 14. Architecture decisions [reviewed]

Extend the e06s01 classifier with a workspace rule set rather than embedding filters in listing code. Reason for Depth: direct reads and recursive discovery require one precedence implementation.

### 15. Test strategy [reviewed]

Table-test precedence, nested rules, negation behavior, dotfiles, traversal, symlink escapes, and omitted-count privacy.

### 16. Observability [reviewed]

Expose counts and stable reason categories only.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Workspace discovery

**Before:** Confined listings expose every entry name and size regardless of sensitivity.

**After:** Listings retain ordinary and exact-process-authorized entries, omit every other protected name and size, and return only an aggregate omitted count using the approved D-01 precedence.

```gherkin
Feature: Private workspace discovery
  Scenario: Rules have deterministic precedence
    Given built-ins, gitignore, OrbitRelay deny rules, and ordinary dotfiles
    When a nested listing is prepared
    Then every path receives the same expected classification as a direct read

  Scenario: Authorized subtree is discoverable
    Given a pre-run sensitive subtree exception
    When that subtree is listed
    Then non-absolute-deny entries inside it are visible and absolute-deny entries remain omitted

  Scenario: Protected entries are opaque
    Given protected entries in a directory
    When the directory is listed
    Then their names and sizes are absent and only the omitted count increases

  Scenario: Confinement remains intact
    Given traversal or a symlink escape
    When discovery applies privacy rules
    Then the original path-safety denial still wins
```

### 18. Dependencies and sequencing [reviewed]

Depends on e06s01; precedes e06s03 and all user exceptions.

### 19. Out of scope [reviewed]

Allow rules in `.orbitrelayignore`, content scanning, model-authored rules, or changing Git itself.

### 20. Definition of done [reviewed]

Precedence and confinement tests pass with no protected-name disclosure or new security finding.

## Implementation Steps

1. Add complete catalog/precedence contracts for built-ins, Git negation, OrbitRelay denies, authorized scope, and dotfiles → verify: `uv run python -m unittest tests.test_workspace_privacy -v`
2. Filter protected entries and expose only an aggregate omitted count → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_tools -v`
3. Prove direct and nested discovery preserve traversal and symlink confinement → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_sandbox tests.test_tools -v`

## Verification Script (Step-by-Step)

1. Build a nested temp workspace containing each rule category.
2. Compare direct-read classification with recursive listing results.
3. Confirm omitted names and sizes do not appear in results or events.
