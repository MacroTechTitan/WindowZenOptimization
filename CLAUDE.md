## Shell conventions

- Commands containing a loop, `$(...)` substitution, a multi-stage pipe, or an
  inline awk/sed program go into a script file, not the command line. Write to
  `scripts/<verb>-<noun>.sh` and run `bash scripts/<name>.sh`.
- Scratch and intermediate files go in `.scratch/` inside the repo, never the OS
  temp directory.
- Scripts take inputs as env vars or `$1`-style args, echo what they are doing,
  and exit non-zero on failure.
