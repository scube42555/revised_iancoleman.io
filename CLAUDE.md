# CLAUDE.md

Offline BIP39 page (iancoleman v0.5.6) extended with **NIGHT - Midnight**, **ADA - Cardano** and **XCH - Chia** coins.
Key derivation lives in Rust compiled to WASM and embedded into one HTML file.

## Build
- `./wasm-derive/build.sh` does everything: cargo build (wasm32) → `wasm-bindgen --target no-modules` →
  `build_html.py vendor/bip39-standalone.html … "BIP39 - Mnemonic Code - Cardano Midnight Chia.html"`.
- `wasm-bindgen-cli` must be exactly **0.2.100** (same as the crate pin in `wasm-derive/Cargo.toml`).
- Commit the rebuilt HTML together with any source change; it is the deliverable.

## Rules
- **Never edit the built HTML or `vendor/` by hand.** `vendor/bip39-standalone.html` is the signed
  upstream release (sha256 `129b0350…695a`). All page changes go through `build_html.py`.
- `build_html.py` uses exact-text anchors (`replace_once` exits if an anchor isn't found exactly once).
  Keep patches small and anchored on stable upstream code.
- Chia crates are pinned exactly (`chia-bls`, `chia-puzzle-types` `=0.55.0`); they share the pinned `blst`.
- Midnight crates are pinned to `midnight-ledger` rev `9f9842e`, matching the sibling CLI project
  `../midnight-offline-derive`. Change the rev in both, or neither.
- `.cargo/config.toml` sets `getrandom_backend="wasm_js"`, and `Cargo.toml` enables the wasm features
  for getrandom 0.2/0.3/0.4. These are needed only to compile; derivation makes no random calls.
- Never put real mnemonics in code, tests, commits or logs. Use the public test vector
  `abandon ×23 art` (optionally with passphrase `TREZOR`).

## Architecture
- `wasm-derive/src/lib.rs` exports:
  - `midnight_row(seedHex, network, path, role)`: BIP32 secp256k1 key at `path`, interpreted by role
    (0/1 unshielded, 2 Dust, 3 Zswap/shielded, 4 metadata)
  - `cardano_root(mnemonic, passphrase)` → 96-byte Icarus root (hex). The page caches it.
  - `cardano_keys(rootHex, account, role)`: root/account/role-level keys
  - `cardano_row(rootHex, network, account, role, index, hardened)`: base / reward address, or CIP-129 DRep ID
  - `chia_keys(seedHex)`: master sk/pk, fingerprint, farmer and pool pk (matches `chia keys show`)
  - `chia_row(seedHex, network, role, index, hardened)`: m/12381/8444/role/index; `xch`/`txch` address for role 2 only.
    Non-wallet roles are always hardened; the wallet is all-hardened or all-unhardened (observer).
  - `derive(input, passphrase)`: full summary in the same shape as the native CLI (used for regression checks)
- Page hooks added by `build_html.py`:
  - `window.altModeChanged` after a coin's `onSelect()`
  - `window.altRow` at the start of each `TableRow`
  - `window.altAfterDisplay` at the end of `displayBip32Info`
  - Midnight and Chia use the page's BIP39 seed (`#seed`); Cardano uses the mnemonic itself (entropy + passphrase).
  - Per-coin page settings (purpose, single tab, default role, networks, roles, texts) live in `CFG` in the controller.
- The Role dropdown drives the hidden `#change-bip44` field, so the page's own path logic still runs.

## Verification (do this after any derivation change)
1. Compare `derive()` output (Node, loading `pkg/`) with the native CLI
   `../midnight-offline-derive/target/x86_64-unknown-linux-musl/release/midnight-offline-derive`
   for the test mnemonic, with and without passphrase. They must match exactly.
2. Cardano: cross-check with `@emurgo/cardano-serialization-lib-nodejs` (install in a scratch dir,
   not in the repo).
3. Chia: cross-check with an independent implementation (e.g. `@noble/curves` BLS12-381 in a scratch dir) and/or
   the `chia_rs` Python wheel in a scratch venv. Note: `chia_rs` key_gen = IETF KeyGen **draft 03** (unhashed salt),
   so the EIP-2333 doc's own test vectors (draft 04) do not apply to the master key.
4. Browser: `chromium --headless=new --dump-dom --virtual-time-budget=…` on a copy of the page with a
   test script injected before `</body>`. Drive coin, network, role and tab changes, then read the table rows.
