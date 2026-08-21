# Activity Pipeline Refinement Backlog

## Current Demo Position

The revised activity pipeline is acceptable for proof-of-concept use. For the demo, the priority is broad coverage across all roles, not perfect activity vocabulary quality.

The current method:
- excludes boilerplate key accountabilities before extraction
- extracts role activities from remaining PD accountabilities
- clusters raw activity labels into a shared vocabulary
- assigns clustered activities back to roles
- exports role/activity links, summaries, vocabulary usage, and a role/activity matrix
- can import first-pass activity assignments into the relational database

## Parked Refinements

### 1. Make Stage 2 role-aware

Status: later refinement.

Current Stage 2 clusters activity phrases mostly by wording. A later version should include role title, classification, branch/unit, source accountability examples, and role distribution when naming, merging, or splitting clusters.

### 2. Separate common generic activities from career-path discriminators

Status: later refinement.

Common activities should remain in the vocabulary, but should not dominate role-linking. A later version should calculate activity frequency, role share, cross-family spread, and inverse-frequency weights.

### 3. Add two-pass vocabulary review

Status: later refinement.

A later version should create candidate clusters first, then review, merge, split, rename, and tag them before Stage 3 assignment. This should produce a human-reviewable vocabulary workbook before assignment.

### 4. Improve Stage 3 shortlist scoring

Status: later refinement.

Current Stage 3 shortlist selection uses local TF-IDF/SVD text similarity. A later version should combine label similarity, raw phrase evidence, source-role evidence, role context, and inverse-frequency weighting.

## Demo Next Step

Run the current revised pipeline over all roles and import first-pass activity assignments into the relational database. Treat the resulting activities as a proof-of-concept dataset to refine after the demo.
