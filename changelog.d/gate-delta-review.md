### Fixed

- **Pipeline gate (stacked tasks).** The gate now checks a stacked task against the dependency's review PASS that the
  task actually contains (the newest PASS record whose SHA is an ancestor of the dependent's reviewed commit), and
  compares the integration order at that SHA's merge point. A later delta review of the dependency at the integration
  HEAD no longer reports "integrated before its dependency" or a missing review PASS for the dependent.
- **Pipeline verdict (delta review).** A task review recorded with `verdict --phase review` at a later SHA of an
  already reviewed task keeps the fallback that dispatch recorded for the task's earlier review, so a same-model delta
  review stays an accepted `SAME_MODEL` note instead of a cross-model blocker. A task never reviewed before still
  needs the dispatch record.
