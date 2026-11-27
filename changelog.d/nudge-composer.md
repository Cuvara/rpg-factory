### Fixed

- **Delivery pipeline: `nudge` counts only a composer-line pointer.** A `Read your task spec at <spec>` pointer now
  counts only when the text before it on its screen line is empty or only composer markers (whitespace and
  `>`, `|`, U+203A, U+276F, U+00BB, U+2502, U+2503), in every join form (newline, space and none for a wrapped path). A
  lead terminal that only echoes `orca worker-start --spec 'Read your task spec at ...'` is no longer reported STUCK and
  `nudge --send` no longer presses Enter in it; an echo above a real composer-line pointer still reports the composer
  line's spec.
