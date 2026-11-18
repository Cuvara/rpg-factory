### Added

- **Pipeline.** `dispatch --note-file FILE` (repeatable) adds the file's text to the session spec verbatim under
  `Session note file <path>:`; a missing, unreadable or blank file exits 2. The lead spec forwards it as
  `--note-file=<path>`.

### Changed

- **Pipeline.** Launch notes travel through the spec file, never the `--prompt` command line: the Orca prompt is only
  `Read your task spec at <path> and follow it.`, and the planner's request and any run lead note go into the spec
  (`Run lead notes:`), covered by the spec file name's digest. cmd.exe misreads parentheses and quotes on the command
  line, which once failed a lead launch with `unknown option '-FilePath'`.
