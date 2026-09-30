# Part 2 - Instance Creation Timing

Instances created from a custom image (from the Part 1 snapshot), machine type `e2-micro`, zone `us-west1-b`.

Time is measured from the `instances.insert` call until the operation reports `DONE`.

| Instance | Time (seconds) |
|---|---|
| lab5-part1-clone-1 | 9.55 |
| lab5-part1-clone-2 | 10.69 |
| lab5-part1-clone-3 | 8.94 |
| **Average** | **9.73** |
