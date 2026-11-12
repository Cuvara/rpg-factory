### Fixed

- **Frontmatter.** The `description` of `skills/pin-bump`, `skills/unity-client-tech` and `commands/assetgen.md` held an unquoted `: `, so the YAML frontmatter did not parse and `claude plugin validate --strict` failed. Each description is now a double-quoted YAML string with the same text.
