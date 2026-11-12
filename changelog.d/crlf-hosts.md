### Fixed

- **Wire parity.** Ignore line endings when comparing Wire.cs files, preventing false differences on Windows checkouts with autocrlf enabled.
- **Registry fragments.** Make the split round trip comparison safe for CRLF checkouts.
- **Art2d workflow.** Use the current Python interpreter for subprocess validation, avoiding the Windows Store python3 stub.
