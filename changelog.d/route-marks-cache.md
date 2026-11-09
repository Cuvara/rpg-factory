### Fixed

- `pipeline_route.available` keyed its cache on the marks file mtime, so a mark set and cleared within the
  timer resolution (Windows CI) returned the stale availability. The key is now the file content.
