### Fixed

- **Artifact lint without jsonschema.** The fallback validator in `scripts/checks/artifact-lint.py` now enforces the
  draft 2020-12 keywords the committed schemas use (`additionalProperties` as a schema, `minProperties`,
  `maxProperties`, `propertyNames`, `maxItems`, `uniqueItems`, `maxLength`, `minimum`, `maximum`, `exclusiveMinimum`,
  `exclusiveMaximum`, `allOf`, `not`, `if`/`then`/`else`, list-valued `type`, `format: date`), so the vfx-style palette
  pattern and the vfx-capture `maxItems` and `maximum` limits are checked on runners without jsonschema.
