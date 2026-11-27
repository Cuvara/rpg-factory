### Fixed

- **Asset-gen.** The workflow.ui.json layout keeps wires out of unrelated nodes: a stage fed past other stages (the staged icon's Save fed by Generate) stays on its source's row, and the skipped stages (the 64 px preview chain) move one row down. X positions, group order and workflow.json are unchanged.
