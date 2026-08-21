# Career Pathways decision log

1. **Identity:** use a stored UUID `role_id`. Database IDs are bootstrap lineage; array positions, titles and PD numbers are never technical keys.
2. **Authority:** canonical CSV tables are the maintained pathway source. The SQLite release is the complete, immutable publication snapshot; JSON and CSV outputs are compatibility exports.
3. **Mappings:** retain every ranked job-family mapping. Primary flattened fields are generated compatibility views only.
4. **Capabilities:** preserve framework, code, name and raw level. Numeric normalisation is separate and reviewable.
5. **Applicability:** capability absence is `review_required` unless a business owner explicitly records `not_applicable`.
6. **Ambiguity:** legacy positional IDs are crosswalked only on unambiguous evidence. No silent title-based collision resolution.
7. **Rebuild:** complete rebuilds are used at the present catalogue size.
8. **Algorithm scope:** the generated graph is a transparent provisional reconciliation artifact. Final pathway-selection tuning awaits the missing algorithm brief and business decisions.
9. **Auditability:** every structured algorithm input, parameter, derived feature, score contribution and recommendation is persisted in the versioned SQLite snapshot.
