// WASM port of midnight-offline-derive/src/main.rs (same derivation logic, same crate revs),
// extended with per-row derivation for the BIP39 page (any account / role / index) and Cardano + Chia keys.
use bech32::{self, ToBase32, Variant};
use bip32::{DerivationPath, XPrv};
use bip39::Mnemonic;
use chia_bls::{DerivableKey, PublicKey as ChiaPk, SecretKey as ChiaSk};
use chia_puzzle_types::{standard::StandardArgs, DeriveSynthetic};
use blake2::{digest::{Update, VariableOutput}, Blake2bVar};
use ed25519_bip32::{DerivationScheme as Scheme, XPrv as EdXPrv};
use midnight_base_crypto::repr::BinaryHashRepr;
use midnight_base_crypto::signatures::SigningKey;
use midnight_coin_structure::coin::UserAddress;
use midnight_ledger::dust::{DustPublicKey, DustSecretKey};
use midnight_serialize::Serializable;
use midnight_zswap::keys::{SecretKeys, Seed};
use std::str::FromStr;
use wasm_bindgen::prelude::*;

const HARD: u32 = 0x8000_0000;

// ---------------------------------------------------------------- helpers

fn b32(hrp: &str, data: &[u8], v: Variant) -> String {
    bech32::encode(hrp, data.to_base32(), v).expect("bech32 encode failed")
}

// Midnight HRP: mainnet has no suffix; every other network appends _{network}
fn mn_hrp(base: &str, net: &str) -> String {
    if net == "mainnet" { base.to_string() } else { format!("{base}_{net}") }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn decode_hex(s: &str) -> Result<Vec<u8>, String> {
    let s = s.trim();
    if s.len() % 2 != 0 {
        return Err("Hex string has odd length".into());
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).map_err(|e| format!("Invalid hex at {i}: {e}")))
        .collect()
}

fn hash224(data: &[u8]) -> [u8; 28] {
    let mut h = Blake2bVar::new(28).unwrap();
    h.update(data);
    let mut out = [0u8; 28];
    h.finalize_variable(&mut out).unwrap();
    out
}

fn js_str(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

fn obj(fields: &[(&str, String)]) -> String {
    let body: Vec<String> = fields.iter().map(|(k, v)| format!("{}:{}", js_str(k), js_str(v))).collect();
    format!("{{{}}}", body.join(","))
}

fn err(e: String) -> JsError {
    JsError::new(&e)
}

// ---------------------------------------------------------------- Midnight

// BIP-32 (secp256k1) private key at an arbitrary path
fn bip32_key(seed: &[u8], path: &str) -> Result<XPrv, String> {
    let p = DerivationPath::from_str(path).map_err(|e| format!("Bad derivation path '{path}': {e}"))?;
    XPrv::derive_from_path(seed, &p).map_err(|e| e.to_string())
}

fn midnight_unshielded(key: &[u8; 32]) -> Result<(Vec<u8>, [u8; 32]), String> {
    let sk = SigningKey::from_bytes(key).map_err(|e| format!("bad signing key: {e:?}"))?;
    let vk = sk.verifying_key();
    let vk_bytes = vk.binary_vec();
    Ok((vk_bytes, UserAddress::from(vk).0 .0))
}

fn midnight_dust(key: &[u8; 32]) -> Result<Vec<u8>, String> {
    let pk = DustPublicKey::from(DustSecretKey::derive_secret_key(&(*key).into()));
    let mut out = Vec::new();
    pk.serialize(&mut out).map_err(|e| e.to_string())?;
    Ok(out)
}

fn midnight_shielded(key: &[u8; 32]) -> Result<Vec<u8>, String> {
    let keys = SecretKeys::from(Seed::from(*key));
    let mut out: Vec<u8> = keys.coin_public_key().0 .0.to_vec();
    keys.enc_public_key().serialize(&mut out).map_err(|e| e.to_string())?;
    Ok(out)
}

/// One Derived Addresses row for Midnight.
/// `path` is the full BIP32 path of the row; `role` selects how the key is interpreted:
/// 0/1 = Night external/internal (unshielded), 2 = Dust, 3 = Zswap (shielded), 4 = Metadata.
#[wasm_bindgen]
pub fn midnight_row(seed_hex: &str, network: &str, path: &str, role: u32) -> Result<String, JsError> {
    let seed = decode_hex(seed_hex).map_err(err)?;
    let xprv = bip32_key(&seed, path).map_err(err)?;
    let key: [u8; 32] = xprv.private_key().to_bytes().into();
    let (address, public_key) = match role {
        0 | 1 => {
            let (vk, addr) = midnight_unshielded(&key).map_err(err)?;
            (b32(&mn_hrp("mn_addr", network), &addr, Variant::Bech32m), hex(&vk))
        }
        2 => {
            let pk = midnight_dust(&key).map_err(err)?;
            (b32(&mn_hrp("mn_dust", network), &pk, Variant::Bech32m), hex(&pk))
        }
        3 => {
            let pk = midnight_shielded(&key).map_err(err)?;
            (b32(&mn_hrp("mn_shield-addr", network), &pk, Variant::Bech32m), hex(&pk))
        }
        4 => ("n/a (metadata key)".to_string(), hex(&xprv.public_key().to_bytes())),
        r => return Err(err(format!("Unknown Midnight role {r}"))),
    };
    Ok(obj(&[("address", address), ("publicKey", public_key), ("privateKey", hex(&key))]))
}

// ---------------------------------------------------------------- Cardano

fn cardano_root_key(input: &str, passphrase: &str) -> Result<EdXPrv, String> {
    let input = input.trim();
    if input.split_whitespace().count() < 2 {
        return Err("Cardano keys need the mnemonic (a hex seed cannot be used)".into());
    }
    let m = Mnemonic::parse(input).map_err(|e| format!("Invalid mnemonic: {e}"))?;
    // Icarus master key: PBKDF2-HMAC-SHA512(password = passphrase, salt = entropy, 4096 iters, 96 bytes)
    let mut master = [0u8; 96];
    pbkdf2::pbkdf2_hmac::<sha2::Sha512>(passphrase.as_bytes(), &m.to_entropy(), 4096, &mut master);
    Ok(EdXPrv::normalize_bytes_force3rd(master))
}

fn root_from_hex(root_hex: &str) -> Result<EdXPrv, String> {
    let b = decode_hex(root_hex)?;
    let arr: [u8; 96] = b.try_into().map_err(|_| "root key must be 96 bytes".to_string())?;
    EdXPrv::from_bytes_verified(arr).map_err(|e| format!("bad root key: {e:?}"))
}

fn cardano_account(root: &EdXPrv, account: u32) -> EdXPrv {
    root.derive(Scheme::V2, HARD | 1852)
        .derive(Scheme::V2, HARD | 1815)
        .derive(Scheme::V2, HARD | account)
}

fn net_id(network: &str) -> u8 {
    if network == "mainnet" { 1 } else { 0 }
}

fn role_prefix(role: u32) -> Result<&'static str, String> {
    match role {
        0 | 1 => Ok("addr"),
        2 => Ok("stake"),
        3 => Ok("drep"),
        r => Err(format!("Unknown Cardano role {r}")),
    }
}

/// Icarus root key (96 bytes hex) from mnemonic + passphrase. Computed once, then reused per row.
#[wasm_bindgen]
pub fn cardano_root(input: &str, passphrase: &str) -> Result<String, JsError> {
    let root = cardano_root_key(input, passphrase).map_err(err)?;
    Ok(hex(root.as_ref()))
}

/// Root, account and role-level keys for the CIP-1852 tab.
#[wasm_bindgen]
pub fn cardano_keys(root_hex: &str, account: u32, role: u32) -> Result<String, JsError> {
    let root = root_from_hex(root_hex).map_err(err)?;
    let acct = cardano_account(&root, account);
    let role_key = acct.derive(Scheme::V2, role);
    Ok(obj(&[
        ("rootXsk", b32("root_xsk", root.as_ref(), Variant::Bech32)),
        ("accountXsk", b32("acct_xsk", acct.as_ref(), Variant::Bech32)),
        ("accountXvk", b32("acct_xvk", acct.public().as_ref(), Variant::Bech32)),
        ("roleXskHex", hex(role_key.as_ref())),
        ("roleXvkHex", hex(role_key.public().as_ref())),
    ]))
}

/// One Derived Addresses row for Cardano: m/1852'/1815'/account'/role/index.
/// Roles 0/1 -> base address (paired with stake key 2/0), 2 -> reward address, 3 -> DRep ID (CIP-129).
#[wasm_bindgen]
pub fn cardano_row(root_hex: &str, network: &str, account: u32, role: u32, index: u32, hardened: bool)
    -> Result<String, JsError>
{
    let root = root_from_hex(root_hex).map_err(err)?;
    let prefix = role_prefix(role).map_err(err)?;
    let acct = cardano_account(&root, account);
    let idx = if hardened { HARD | index } else { index };
    let key = acct.derive(Scheme::V2, role).derive(Scheme::V2, idx);
    let vk = key.public().public_key();
    let nid = net_id(network);
    let address = match role {
        0 | 1 => {
            let stake = acct.derive(Scheme::V2, 2).derive(Scheme::V2, 0);
            let mut base = vec![nid];
            base.extend_from_slice(&hash224(&vk));
            base.extend_from_slice(&hash224(&stake.public().public_key()));
            b32(if nid == 1 { "addr" } else { "addr_test" }, &base, Variant::Bech32)
        }
        2 => {
            let mut reward = vec![0xE0 | nid];
            reward.extend_from_slice(&hash224(&vk));
            b32(if nid == 1 { "stake" } else { "stake_test" }, &reward, Variant::Bech32)
        }
        _ => {
            // CIP-129 DRep ID: header 0x22 (DRep, key hash) ++ blake2b-224(vk)
            let mut id = vec![0x22];
            id.extend_from_slice(&hash224(&vk));
            b32("drep", &id, Variant::Bech32)
        }
    };
    Ok(obj(&[
        ("address", address),
        ("publicKey", b32(&format!("{prefix}_vk"), &vk, Variant::Bech32)),
        ("privateKey", b32(&format!("{prefix}_xsk"), key.as_ref(), Variant::Bech32)),
    ]))
}

// ---------------------------------------------------------------- Chia

// Chia key paths (chia-blockchain derive_keys.py): m/12381/8444/<role>/<index>
const CHIA_ROLES: [u32; 5] = [0, 1, 2, 3, 5]; // farmer, pool, wallet, local (plot), pool singleton (plot NFT owner)
const CHIA_WALLET: u32 = 2;

/// BLS (EIP-2333) master key from the BIP39 seed, as chia-blockchain does (AugSchemeMPL.key_gen(seed)).
fn chia_master(seed_hex: &str) -> Result<ChiaSk, String> {
    let seed = decode_hex(seed_hex)?;
    if seed.len() < 32 {
        return Err("Chia needs a seed of at least 32 bytes".into());
    }
    Ok(ChiaSk::from_seed(&seed))
}

/// Chia derives the wallet role either fully unhardened ("observer", the default wallet)
/// or fully hardened; every other role is always hardened.
fn chia_key(master: &ChiaSk, role: u32, index: u32, hardened: bool) -> ChiaSk {
    let path = [12381, 8444, role, index];
    if hardened || role != CHIA_WALLET {
        path.iter().fold(master.clone(), |k, i| k.derive_hardened(*i))
    } else {
        path.iter().fold(master.clone(), |k, i| k.derive_unhardened(*i))
    }
}

/// xch/txch address of the standard transaction puzzle for a wallet public key.
fn chia_address(pk: &ChiaPk, network: &str) -> String {
    let puzzle_hash: [u8; 32] = StandardArgs::curry_tree_hash(pk.derive_synthetic()).into();
    b32(if network == "mainnet" { "xch" } else { "txch" }, &puzzle_hash, Variant::Bech32m)
}

/// Master-level values shown by `chia keys show`.
#[wasm_bindgen]
pub fn chia_keys(seed_hex: &str) -> Result<String, JsError> {
    let master = chia_master(seed_hex).map_err(err)?;
    let pk = master.public_key();
    Ok(obj(&[
        ("masterSk", hex(&master.to_bytes())),
        ("masterPk", hex(&pk.to_bytes())),
        ("fingerprint", pk.get_fingerprint().to_string()),
        ("farmerPk", hex(&chia_key(&master, 0, 0, true).public_key().to_bytes())),
        ("poolPk", hex(&chia_key(&master, 1, 0, true).public_key().to_bytes())),
    ]))
}

/// One Derived Addresses row for Chia: m/12381/8444/role/index. Only the wallet role (2) has an address.
#[wasm_bindgen]
pub fn chia_row(seed_hex: &str, network: &str, role: u32, index: u32, hardened: bool) -> Result<String, JsError> {
    if !CHIA_ROLES.contains(&role) {
        return Err(err(format!("Unknown Chia role {role}")));
    }
    let master = chia_master(seed_hex).map_err(err)?;
    let sk = chia_key(&master, role, index, hardened);
    let pk = sk.public_key();
    let address = if role == CHIA_WALLET { chia_address(&pk, network) } else { "n/a (key only)".to_string() };
    Ok(obj(&[("address", address), ("publicKey", hex(&pk.to_bytes())), ("privateKey", hex(&sk.to_bytes()))]))
}

// ---------------------------------------------------------------- full summary (regression check vs native CLI)

/// Same output as the native midnight-offline-derive CLI, as JSON. `input` = mnemonic or hex seed.
#[wasm_bindgen]
pub fn derive(input: &str, passphrase: &str) -> Result<String, JsError> {
    let input = input.trim();
    let seed = if input.split_whitespace().count() > 1 {
        let m = Mnemonic::parse(input).map_err(|e| err(format!("Invalid mnemonic: {e}")))?;
        hex(&m.to_seed(passphrase))
    } else {
        input.to_string()
    };
    let root = if input.split_whitespace().count() > 1 { Some(cardano_root(input, passphrase)?) } else { None };
    let row = |net: &str, role: u32| -> Result<String, JsError> {
        let r = midnight_row(&seed, net, &format!("m/44'/2400'/0'/{role}/0"), role)?;
        Ok(r.split("\"address\":\"").nth(1).unwrap().split('"').next().unwrap().to_string())
    };
    let dust_pk = {
        let r = midnight_row(&seed, "mainnet", "m/44'/2400'/0'/2/0", 2)?;
        r.split("\"publicKey\":\"").nth(1).unwrap().split('"').next().unwrap().to_string()
    };
    let mut nets = Vec::new();
    for net in ["mainnet", "preprod", "testnet"] {
        let (base, reward) = match &root {
            Some(rh) => {
                let a = |role: u32| -> Result<String, JsError> {
                    let r = cardano_row(rh, net, 0, role, 0, false)?;
                    Ok(r.split("\"address\":\"").nth(1).unwrap().split('"').next().unwrap().to_string())
                };
                (js_str(&a(0)?), js_str(&a(2)?))
            }
            None => ("null".into(), "null".into()),
        };
        nets.push(format!(
            "{{\"network\":{},\"cardanoBase\":{},\"cardanoReward\":{},\"unshielded\":{},\"shielded\":{},\"dust\":{}}}",
            js_str(net), base, reward, js_str(&row(net, 0)?), js_str(&row(net, 3)?), js_str(&row(net, 2)?)
        ));
    }
    Ok(format!(
        "{{\"dustPublicKeyHex\":{},\"dustPublicKeyLen\":{},\"networks\":[{}]}}",
        js_str(&dust_pk), dust_pk.len() / 2, nets.join(",")
    ))
}
