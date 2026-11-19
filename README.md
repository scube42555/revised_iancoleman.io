# BIP39 Mnemonic Code — Cardano + Midnight + Chia

A single, self-contained, **offline** HTML page based on
[Ian Coleman's BIP39 tool](https://github.com/iancoleman/bip39) (v0.5.6), extended with three coins:

- **NIGHT - Midnight**: unshielded, Dust and shielded (Zswap) addresses and keys
- **ADA - Cardano**: payment, change, stake and DRep keys and addresses (CIP-1852)
- **XCH - Chia**: BLS wallet keys and `xch` addresses, plus farmer, pool, local and singleton keys

The Midnight, Cardano and Chia key derivation is done by Rust code compiled to WebAssembly and embedded
in the page. It uses the same `midnight-ledger` crates (pinned to rev `9f9842e`) as the
`midnight-offline-derive` CLI, so its output matches that tool exactly. Chia uses the official
[`chia_rs`](https://github.com/Chia-Network/chia_rs) crates (`chia-bls`, `chia-puzzle-types` 0.55.0), the same
code the Chia reference wallet runs.

> **Security:** this page handles mnemonics and private keys. Download it, verify it, then use it
> **only on an offline / air-gapped machine**. Never enter a mnemonic that holds real funds on an
> internet-connected computer.

## Usage

Open `BIP39 - Mnemonic Code - Cardano Midnight Chia.html` in a browser (no server needed). Enter or
generate a mnemonic and optional passphrase, then pick a coin:

### NIGHT - Midnight
- **Network:** mainnet, preprod, preview, testnet, undeployed (changes the address prefix, e.g. `mn_addr_preprod1…`).
- **Derivation Path:** BIP32 and **BIP44 (Midnight)** tabs only. In the BIP44 tab, *External / Internal*
  is replaced by **Role**:

  | Role | Meaning | Address |
  |---|---|---|
  | 0 | Unshielded (Night external) | `mn_addr…` |
  | 1 | Unshielded change (Night internal) | `mn_addr…` |
  | 2 | Dust | `mn_dust…` |
  | 3 | Shielded (Zswap) | `mn_shield-addr…` |
  | 4 | Metadata | key only |

- **Derived Addresses:** `m/44'/2400'/account'/role/index`. Keys are BIP32 secp256k1 from the BIP39 seed.
  For Dust and Shielded, the "Private Key" column is the 32-byte BIP32 key used as the *role seed*,
  from which Midnight derives its Dust / Zswap keys.
- On the BIP32 tab (custom path), the role is taken from the 4th path level if it is 0–4;
  otherwise from the Role selector.

### ADA - Cardano
- **Network:** mainnet, preprod, preview (preprod and preview share network id 0, so their addresses are identical).
- **Derivation Path:** a single **CIP-1852** tab: `m/1852'/1815'/account'/role/index` with
  **Role** = 0 Payment, 1 Change, 2 Stake, 3 DRep.
- Keys are BIP32-**Ed25519** (Icarus): root = PBKDF2-HMAC-SHA512(passphrase, mnemonic *entropy*, 4096, 96 bytes).
  The page's BIP39 Seed is **not** used for Cardano; the Root Key field shows `root_xsk…` instead.
- **Derived Addresses:**
  - Payment / Change: base address, paired with stake key `…/2/0`
  - Stake: reward address (`stake1…`)
  - DRep: CIP-129 DRep ID (`drep1…`)
  - Keys in CIP-5 bech32 (`addr_vk` / `addr_xsk`, `stake_…`, `drep_…`)

### XCH - Chia
- **Network:** mainnet (`xch1…`), testnet11 (`txch1…`).
- **Derivation Path:** a single **EIP-2333 (Chia)** tab: `m/12381/8444/role/index` (Chia has no account level),
  with **Role** = 2 Wallet (default), 0 Farmer, 1 Pool, 3 Local / plot, 5 Pool singleton (plot NFT owner).
- Keys are BLS12-381. Master key = `AugSchemeMPL.key_gen(BIP39 seed)` (IETF BLS KeyGen draft 03, which is what
  `chia_rs` implements; it differs from the draft-04 KeyGen in the EIP-2333 test vectors). Children are EIP-2333
  hardened, or Chia's unhardened derivation.
- **Use hardened addresses** unchecked = observer (unhardened) wallet keys, the Chia wallet's default;
  checked = hardened wallet keys (`m/12381'/8444'/2'/i'`). Farmer, pool, local and singleton keys are always hardened.
- The key fields show what `chia keys show` prints: master private key, fingerprint, master public key, farmer and pool public keys.
- **Derived Addresses:** wallet rows show the standard-transaction address (bech32m of the puzzle hash of
  `p2_delegated_puzzle_or_hidden_puzzle` curried with the synthetic key); other roles are key only.
  Public keys are 48-byte G1 (hex) and private keys are 32 bytes (hex).
- The Chia wallet uses an **empty** BIP39 passphrase; any passphrase changes every key.

## Verifying the page

`vendor/bip39-standalone.html` is the unmodified official release 0.5.6, with its signed checksum:

```sh
sha256sum vendor/bip39-standalone.html
# 129b03505824879b8a4429576e3de6951c8599644c1afcaae80840f79237695a
gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys 5AD5C88083708E93A2966FF49FF1B58CA7B9E6A5
gpg --verify vendor/signature.txt.asc
```

The built page is reproducible from that file plus the code in `wasm-derive/` (see below), so you
can rebuild it yourself and compare it with the committed copy. Builds are byte-identical with the
same toolchain; the committed page was built with rustc 1.98.1 and wasm-bindgen 0.2.100.

## Building

Requirements: Rust (with the `wasm32-unknown-unknown` target), `wasm-bindgen-cli` **0.2.100**
(must match the `wasm-bindgen` crate version), Python 3.

```sh
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version 0.2.100 --locked
./wasm-derive/build.sh
```

`build.sh` compiles the WASM module, generates the JS glue, and runs `build_html.py`. That script
patches `vendor/bip39-standalone.html` into `BIP39 - Mnemonic Code - Cardano Midnight Chia.html`.

## Layout

```
BIP39 - Mnemonic Code - Cardano Midnight Chia.html   built page (commit after every rebuild)
vendor/                                              official upstream release + signature + MIT license
wasm-derive/src/lib.rs                               Midnight + Cardano + Chia derivation (Rust -> WASM)
wasm-derive/build_html.py                            patches the upstream page (coins, selectors, hooks)
wasm-derive/build.sh                                 full rebuild
```

## Credits and license

This project is MIT licensed; see `LICENSE`.

Based on [iancoleman/bip39](https://github.com/iancoleman/bip39), MIT License (Copyright (c) 2014-2016 Ian Coleman); see `vendor/LICENSE-bip39`.
Midnight key derivation uses [midnightntwrk/midnight-ledger](https://github.com/midnightntwrk/midnight-ledger).
Chia key derivation uses [Chia-Network/chia_rs](https://github.com/Chia-Network/chia_rs) (Apache-2.0).
