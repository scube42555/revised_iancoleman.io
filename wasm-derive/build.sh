#!/usr/bin/env bash
# Rebuild the WASM module and regenerate the patched page.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
wasm-bindgen --target no-modules --no-typescript --out-dir pkg target/wasm32-unknown-unknown/release/midnight_derive_wasm.wasm
python3 build_html.py ../vendor/bip39-standalone.html pkg/midnight_derive_wasm.js pkg/midnight_derive_wasm_bg.wasm \
  "../BIP39 - Mnemonic Code - Cardano Midnight.html"
