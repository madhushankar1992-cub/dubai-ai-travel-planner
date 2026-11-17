# Catalog schema 1

`repository.SCHEMA` is the executable, idempotent initial migration. It records migration 1 and creates immutable dataset versions plus a single active pointer. All catalog contents are validated typed JSON; operational run/event tables are deferred until their implementation phases. Each import activates its version in the same transaction. Reusing a version with changed content is rejected. Re-importing identical content does not duplicate it.
