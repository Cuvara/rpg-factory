### Added

- **Run-all slot progress.** `tests/run-all.sh` keeps a `progress` file in its test slot (the check that is running or
  last finished, its result, the passed and failed counts so far, a UTC time); it goes with the slot.
  `factory-pipeline.py status` shows each slot holder's last check, counts and the age of the update, so a live run is
  not mistaken for an orphan. The line still says the user decides and the run never stops it.
