# Code, documentation and repository audit

Reviewed 13–14 November 2026 against source baseline `e257654` (v0.0.18).
Work is on `codex/full-audit-refactor`; the released v0.0.18 binaries do not contain these fixes.

## Scope and method

Reviewed the codec/model and editing operations, CSV/report workflows, desktop worker lifecycle,
firmware loader and transport resource handling, browser renderer, documentation and CI/build
configuration. Parallel reviews were checked against the owning source and reproduced with offline
regressions. The existing suite passed at baseline: **521 passed, 3 warnings** with private fixtures.

No physical device was accessed. Firmware flashing, EEPROM changes, destructive commands and
external-device exchanges were not exercised. The Windows popup workaround remains unverified on
a physical Windows desktop. This audit is not evidence of complete original-editor or hardware parity.

## Findings fixed

| Priority | Finding and consequence | Change / regression evidence |
|---|---|---|
| P1 | A CSV row could update names and earlier cells before a later invalid cell failed; the caller reported zero applied rows despite changed data. Numeric masking also silently wrapped invalid references and bytes. | Parse each complete row into a detached record and commit only after validation. Reject out-of-range song/preset references, links and bytes. `tests/test_data_integrity.py`. |
| P1 | Reordering a preset or song moved the parent payload but left linked labels attached to the old number. | Move extension types 9/10/11 with the parent; cover sparse extensions, serialization and both reference-sync modes. Reject missing or duplicate parent numbering before mutation. `tests/test_data_integrity.py`. |
| P1 | The firmware file could change after validation and different bytes could reach the MIDI port. | Bind the outgoing byte count and SHA-256 to the approved report before any MIDI I/O. `tests/test_firmware_comms_audit_regressions.py`. |
| P1 | Closing the firmware window during its daemon worker could interrupt flashing; preparation failure could leave the window permanently busy. | Reject close while sending, restore controls on preparation errors, capture port/report on the GUI thread. Offline GUI regressions. |
| P1 | Menus/headers could start another device worker or replace/edit the current document while an earlier worker still used it. | Guard task overlap/disconnect/quit/calibration, disable editing and document entry points while busy, snapshot outgoing frames, preserve exact successful-write baselines, restore controls after worker or callback exceptions. `tests/test_ui_refresh_task_regressions.py`, `tests/test_ui_worker_document_regressions.py`. |
| P2 | A backup with a truncated last frame could be opened and saved without that frame. Bytes between/after complete frames were silently lost. Invalid nibble data could be decoded and normalized on save. | Reject incomplete or malformed records; preserve non-frame envelope bytes in `Dump` without adding them to individual device-write frames. `tests/test_codec_validation.py`. |
| P2 | A stale ACK could establish an editor session; per-record replies were accepted without matching the requested record identity. | Check the handshake reply family/device, stop a full pull after handshake failure, match type/number/device/subtype on per-record reads and count invalid replies toward the miss limit. `tests/test_reply_association.py`. |
| P2 | Coalesced serial replies lost everything after the first frame. Incomplete bulk record tails were silently discarded. | Retain trailing serial bytes for later reads, clear them on flush, reject non-record-aligned bulk data. Offline transport regressions. |
| P2 | Failure opening a second MIDI endpoint leaked the first endpoint. An odd firmware image length crashed instead of reaching normal validation. | Close already-open ports on setup failure; preserve unmatched bytes during firmware pair swapping. Firmware/comms regressions. |
| P2 | Refreshing MIDI channel context rebuilt IA-Map/Song/Set-List dropdowns and reset their visible selections. | Re-load the bound values after rebuilding slot-picker choices; no data mutation or dirty signal. UI refresh regressions. |
| P2 | Browser navigation accumulated dependent-enum listeners until another data edit happened. | Abort the previous render's event listeners when the next tab renders. `tests/test_web_listener_regressions.py` executes repeated navigation in Node. |
| P2 | Reports resolved references by list position, so sparse or unordered backups could display another record's name. | Resolve report names by stored record number; keep all report generation read-only. `tests/test_reports.py`. |
| P2 | New factory-based IA report tests inherited a module-wide private-rig skip, so public CI did not run them. | Move report tests to an independent module using bundled factory data; limit private-fixture skips to tests that need them. |
| P2 | User/parity/web docs still claimed several USB types were blocked and implemented browser tools were missing. | Correct the guides against current source and distinguish implementation from hardware validation. |

## Refactor boundaries and compatibility

- `lfeditor/reports.py` owns read-only report generation. Existing callers of
  `lfeditor.csvio.report_text` / `write_report` keep working through compatible imports.
- CSV parsing remains in `csvio.py`; failures apply nothing from the rejected row, while later valid
  rows can still import. Each data row must have the export format's column count. Previously
  accepted malformed or wrapped numbers now produce warnings.
- Whole-backup parsing is strict about incomplete/malformed frames. Valid fixture round trips retain
  their byte fidelity. `split_frames` remains a tolerant stream helper for existing callers.
- Reordering supports complete consecutive parent numbering (regardless of file order), and sparse
  linked labels. Command-table reference rewriting is still incomplete; do not infer universal
  reference synchronization from the label fix.
- Original remains the default name-update mode. No new protocol write operation is enabled.
- Device work remains in worker threads; data editing is temporarily locked while a transfer runs.

## Repository and build review

- The working tree tracks source, docs, tests and bundled factory defaults. No release ZIP/EXE/DMG/JAR/
  BIN/log/cache files were found in the current tracked tree. `reference/`, `packaging/`, local captures
  and the generated web bundle are ignored.
- **Unresolved historical firmware ZIP:** commits `4bd4dc2` and `b91a0c7` still record its addition and
  removal. Previous attempted cleanup was reset at the user's request. No history rewrite was
  performed in this audit; remote refs, clones/forks and GitHub caches need separate handling.
- Source CI tests Python 3.12 on Linux, Windows and macOS (`macos-15`). Baseline v0.0.18 source CI and
  Pages deployment were green when checked. This audit's validation is recorded below separately.
- Packaging is owned by `famc-liquid-foot-editor-builds`; its workflow checks out the source ref and
  overlays packaging, then runs frozen-binary selftests. A source push is not a desktop release.
- The packaging workflow can accept a moving ref such as `main`. Use a tested source SHA when cutting
  the next release. Dependencies have lower bounds without a locked build environment, so old
  releases are not guaranteed reproducible. Locking/updating dependencies requires a separate policy.
- Pages builds the Pyodide package from source and deploys on relevant main pushes. First use needs
  network access to fetch Pyodide and the bundle; no service worker provides guaranteed offline reloads.

## Remaining work

1. Hardware validation of the parser/reply changes and all recovered protocol commands remains a
   separate bench task (see [HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md)).
2. A bulk reply truncated exactly at a record boundary can still look valid; expected record counts
   vary across devices/firmware and need capture-backed completeness checks before changing fallback.
3. Reordering does not rewrite all programming-command references; their parameter encoding must be
   verified before implementing that behavior.
4. External Device Definitions, external-device sync import, selective export and Undo/Redo remain
   feature gaps (see [ORIGINAL_EDITOR_GAP_ANALYSIS.md](ORIGINAL_EDITOR_GAP_ANALYSIS.md)).
5. The two large desktop modules (`app.py`, `fields.py`) remain candidates for incremental extraction.
   This pass extracts reporting and addresses defects; it does not rewrite the entire UI framework.
6. The Windows Fusion menu workaround still needs visual confirmation from a Windows user.

## Validation

Validation on macOS, 14 November 2026:

- Full local suite with private fixtures: **583 passed, 3 dependency deprecation warnings**. Two
  additional report regressions were added afterwards; the focused audit suite including those
  passed **70 tests**. The final source collects **585 tests** locally.
- A separate copy of only tracked/public source plus the audit additions (no `reference/` or captured
  golden files): **282 passed, 170 skipped, 3 dependency warnings**. This includes all new report
  tests; the skipped tests require private fixtures or hardware-specific prerequisites.
- Editor selftest: passed (384 factory presets, 11 tabs). Firmware-loader selftest: passed
  (241 known hashes; dry-run/refusal paths only, no MIDI I/O).
- Python compilation, Node syntax check and the renderer listener-lifecycle regression passed.
- Pyodide bundle rebuilt successfully, including the extracted reports module (70 package files).
- Relative file links checked across README, USER_GUIDE and 21 top-level docs: no missing targets.
- `git diff --check` passed.

Remote all-OS results are tracked by the audit branch's GitHub Actions run. No release was cut as
part of this audit; the current public desktop release remains v0.0.18.
