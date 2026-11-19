#!/usr/bin/env python3
"""Patch the iancoleman BIP39 page: add "NIGHT - Midnight", "ADA - Cardano" and "XCH - Chia" coins whose
Derivation Path / Derived Addresses sections are computed by the embedded WASM module.

usage: build_html.py <source.html> <glue.js> <module.wasm> <out.html>
"""
import base64, sys

src, glue_path, wasm_path, out = sys.argv[1:5]
html = open(src, encoding="utf-8").read()
glue = open(glue_path, encoding="utf-8").read()
wasm_b64 = base64.b64encode(open(wasm_path, "rb").read()).decode()


def replace_once(s, old, new):
    n = s.count(old)
    if n != 1:
        sys.exit(f"patch anchor found {n} times (expected 1): {old[:70]!r}")
    return s.replace(old, new)


def strip_snapshot_options(s, select_open):
    """The saved page contains a snapshot of the JS-populated <option>s; drop it so the
    populate*Select() functions don't add a second copy on load."""
    start = s.index(select_open)
    end = s.index("</select>", start)
    o1 = s.index("<option", start)
    if select_open.startswith('<select id="bip32-client"'):
        o1 = s.index("<option", s.index("</option>", o1))  # keep "Custom derivation path"
    return s[:o1] + s[end:] if o1 < end else s


html = strip_snapshot_options(html, '<select id="network-phrase" class="network form-control">')
html = strip_snapshot_options(html, '<select id="bip32-client" class="client form-control">')

# ---- 1. coins (appended to the end of the networks array: no index shift for other coins)
html = replace_once(html,
    '''                setHdCoin(559);
            },
        }
    ]''',
    '''                setHdCoin(559);
            },
        },
        {
            name: "NIGHT - Midnight",
            onSelect: function() {
                network = libs.bitcoin.networks.bitcoin;
                setHdCoin(2400);
            },
        },
        {
            name: "ADA - Cardano",
            onSelect: function() {
                network = libs.bitcoin.networks.bitcoin;
                setHdCoin(1815);
            },
        },
        {
            name: "XCH - Chia",
            onSelect: function() {
                network = libs.bitcoin.networks.bitcoin;
                setHdCoin(8444);
            },
        }
    ]''')

# ---- 2. Network selector + notes, directly below the Coin selector
NETWORK_GROUP = '''
                        <div id="alt-network-group" class="form-group hidden">
                            <label for="alt-network" class="col-sm-2 control-label">Network</label>
                            <div class="col-sm-10">
                                <select id="alt-network" class="form-control"></select>
                                <p class="help-block" id="alt-help"></p>
                            </div>
                        </div>'''
start = html.index('<select id="network-phrase"')
pos = html.index("</select>", start)
pos = html.index("</div>", pos)              # close col-sm-10
pos = html.index("</div>", pos + 6) + 6      # close form-group
html = html[:pos] + NETWORK_GROUP + html[pos:]

# ---- 3. Role selector in the BIP44 tab, right after the External / Internal field
ROLE_GROUP = '''
                                <div id="alt-role-group" class="form-group hidden">
                                    <label for="alt-role" class="col-sm-2 control-label">Role</label>
                                    <div class="col-sm-10">
                                        <select id="alt-role" class="form-control"></select>
                                    </div>
                                </div>'''
pos = html.index('<input id="change-bip44"')
pos = html.index("</div>", pos)
pos = html.index("</div>", pos + 6) + 6
html = html[:pos] + ROLE_GROUP + html[pos:]

# ---- 4. hooks into the page's own logic
# mode switch runs right after a coin's onSelect(), before the page recomputes
html = replace_once(html,
    '''        var network = networks[networkIndex];
        network.onSelect();''',
    '''        var network = networks[networkIndex];
        network.onSelect();
        if (window.altModeChanged) { window.altModeChanged(); }''')
# each Derived Addresses row: let the Midnight/Cardano/Chia code produce it
html = replace_once(html,
    '''                if (!self.shouldGenerate) {
                    return;
                }
                // derive HDkey for this row of the table''',
    '''                if (!self.shouldGenerate) {
                    return;
                }
                if (window.altRow) {
                    var alt = window.altRow(index, useHardenedAddresses);
                    if (alt) {
                        addAddressToList(alt.path, alt.address, alt.publicKey, alt.privateKey);
                        if (isLast) {
                            hidePending();
                            updateCsv();
                        }
                        return;
                    }
                }
                // derive HDkey for this row of the table''')
# after keys are displayed: Cardano and Chia replace the secp256k1 key fields with their own
html = replace_once(html,
    '''        if (isELA()) {
            displayBip32InfoForELA();
        }
    }''',
    '''        if (isELA()) {
            displayBip32InfoForELA();
        }
        if (window.altAfterDisplay) { window.altAfterDisplay(); }
    }''')

# ---- 5. controller
CONTROLLER = r'''
(function() {
    var COINS = { "NIGHT - Midnight": "midnight", "ADA - Cardano": "cardano", "XCH - Chia": "chia" };
    // purpose: value of the Purpose field; singleTab: hide the BIP32 tab too; defaultRole: initial Role selection
    var CFG = {
        midnight: {
            purpose: 44, singleTab: false, defaultRole: 0,
            networks: ["mainnet", "preprod", "preview", "testnet", "undeployed"],
            roles: [[0, "0 - Unshielded (Night external)"], [1, "1 - Unshielded change (Night internal)"],
                    [2, "2 - Dust"], [3, "3 - Shielded (Zswap)"], [4, "4 - Metadata (key only, no address)"]],
            tab: "BIP44 (Midnight)",
            spec: 'Midnight HD wallet: BIP32 secp256k1 keys from the BIP39 seed at m/44\'/2400\'/account\'/role/index. ' +
                  'For Dust and Shielded roles the "Private Key" column is the 32-byte BIP32 key used as the role seed, ' +
                  'from which Midnight derives its Dust / Zswap keys.',
            help: 'Unshielded public key = Schnorr verifying key; Dust public key = 33-byte serialized Dust key; ' +
                  'Shielded public key = coin public key + encryption public key (the shielded address payload). ' +
                  'On the BIP32 tab the role is taken from the 4th path level when it is 0-4, otherwise from the Role selector.'
        },
        cardano: {
            purpose: 1852, singleTab: true, defaultRole: 0,
            networks: ["mainnet", "preprod", "preview"],
            roles: [[0, "0 - Payment (external)"], [1, "1 - Change (internal)"], [2, "2 - Stake"], [3, "3 - DRep"]],
            tab: "CIP-1852",
            spec: 'Cardano HD wallet (CIP-1852): BIP32-Ed25519 (Icarus) root key = PBKDF2-HMAC-SHA512(passphrase, mnemonic entropy, 4096, 96 bytes); ' +
                  'path m/1852\'/1815\'/account\'/role/index. Keys use the CIP-5 bech32 formats.',
            help: 'Cardano does not use the BIP39 Seed or BIP32 Root Key shown by this page; the Root Key field shows the Icarus root_xsk instead. ' +
                  'Payment and Change rows show base addresses paired with the stake key m/1852\'/1815\'/account\'/2/0. ' +
                  'Stake rows show reward addresses; DRep rows show the CIP-129 DRep ID. ' +
                  'preprod and preview share network id 0, so their addresses are identical.'
        },
        chia: {
            purpose: 12381, singleTab: true, defaultRole: 2,
            networks: ["mainnet", "testnet11"],
            roles: [[2, "2 - Wallet"], [0, "0 - Farmer (key only)"], [1, "1 - Pool (key only)"],
                    [3, "3 - Local / plot (key only)"], [5, "5 - Pool singleton / plot NFT owner (key only)"]],
            tab: "EIP-2333 (Chia)",
            spec: 'Chia HD wallet: BLS12-381 keys. Master key = BLS KeyGen (chia_rs AugSchemeMPL.key_gen) of the BIP39 seed; ' +
                  'path m/12381/8444/role/index, as in chia-blockchain. Wallet addresses are bech32m of the standard ' +
                  'transaction puzzle hash (synthetic key with the default hidden puzzle).',
            help: 'Unchecked "Use hardened addresses" = observer (unhardened) wallet keys, which the Chia wallet uses by default; ' +
                  'checked = hardened wallet keys (the wallet tracks both). Farmer, pool, local and singleton keys are always hardened. ' +
                  'The fields above match "chia keys show". The official Chia wallet uses an empty BIP39 passphrase; ' +
                  'any passphrase entered here changes every key.'
        }
    };
    var current = null, saved = null, ready = false;
    var netChoice = { midnight: "mainnet", cardano: "mainnet", chia: "mainnet" };
    var rootCache = { key: null, value: null, error: null };

    var bytes = Uint8Array.from(atob(MIDNIGHT_WASM_B64), function(c) { return c.charCodeAt(0); });
    wasm_bindgen(bytes).then(function() { ready = true; recompute(); })
        .catch(function(e) { $("#alt-help").text("Failed to load WASM module: " + e); });

    function mode() {
        var t = $("#network-phrase option:selected").text();
        return COINS[t] || null;
    }
    function recompute() {
        if ($("#phrase").val().trim() || $("#seed").val().trim()) {
            $("#change-bip44").trigger("input");
        }
    }
    function errText(e) { return "Error: " + (e && e.message ? e.message : e); }

    // Elements whose text we change, saved once so another coin restores them.
    var EL = {
        tab: function() { return $("#bip44-tab a"); },
        spec: function() { return $("#bip44 > form > .col-sm-10 > p").first(); },
        purposeLabel: function() { return $('label[for="purpose-bip44"]'); },
        acctHelp: function() { return $("#bip44 p").filter(function() { return /account extended keys/.test($(this).text()); }); },
        rootLabel: function() { return $('label[for="root-key"]'); },
        xprvLabel: function() { return $('#bip44 label[for="account-xprv"] span').first(); },
        xpubLabel: function() { return $('#bip44 label[for="account-xpub"] span').first(); },
        extPrivLabel: function() { return $('label[for="extended-priv-key"]'); },
        extPubLabel: function() { return $('label[for="extended-pub-key"]'); },
        pathLabel: function() { return $('label[for="bip44-path"]'); }
    };
    function saveOriginals() {
        if (saved) { return; }
        saved = {};
        for (var k in EL) { saved[k] = EL[k]().html(); }
    }
    function setText(k, text) { EL[k]().text(text); }

    window.altModeChanged = function() {
        saveOriginals();
        var m = mode();
        current = m;
        var cfg = m ? CFG[m] : null;
        var tabsToHide = m ? ["#bip49-tab", "#bip84-tab", "#bip141-tab"] : [];
        if (m && cfg.singleTab) { tabsToHide.push("#bip32-tab"); }
        ["#bip32-tab", "#bip49-tab", "#bip84-tab", "#bip141-tab"].forEach(function(id) {
            $(id).toggleClass("hidden", tabsToHide.indexOf(id) >= 0);
        });
        $("#alt-network-group, #alt-role-group").toggleClass("hidden", !m);
        $("#change-bip44").closest(".form-group").toggleClass("hidden", !!m);
        $("#account-bip44").closest(".form-group").toggleClass("hidden", m === "chia");  // Chia has no account level
        for (var k in EL) { EL[k]().html(saved[k]); }
        $("#purpose-bip44").val(m ? cfg.purpose : 44);
        if (!m) { $("#change-bip44").val(0); return; }

        var net = $("#alt-network").empty();
        cfg.networks.forEach(function(n) { net.append($("<option>").val(n).text(n)); });
        net.val(netChoice[m]);
        var role = $("#alt-role").empty();
        cfg.roles.forEach(function(r) { role.append($("<option>").val(r[0]).text(r[1])); });
        role.val(String(cfg.defaultRole));
        $("#change-bip44").val(cfg.defaultRole);
        setText("tab", cfg.tab);
        setText("spec", cfg.spec);
        $("#alt-help").text(cfg.help);
        if (m === "cardano") {
            setText("rootLabel", "Cardano Root Key (root_xsk)");
            setText("acctHelp", "Account keys in CIP-5 bech32 (acct_xsk = 96-byte extended private key incl. chain code; acct_xvk = public key + chain code).");
            setText("xprvLabel", "Account Extended Private Key (acct_xsk)");
            setText("xpubLabel", "Account Extended Public Key (acct_xvk)");
            setText("extPrivLabel", "Role Extended Private Key (hex)");
            setText("extPubLabel", "Role Extended Public Key (hex)");
            setText("pathLabel", "CIP-1852 Derivation Path");
        }
        if (m === "chia") {
            setText("rootLabel", "Chia Master Private Key (hex)");
            setText("acctHelp", "Master key details, as printed by \"chia keys show\".");
            setText("xprvLabel", "Fingerprint");
            setText("xpubLabel", "Master Public Key (m)");
            setText("extPrivLabel", "Farmer Public Key (m/12381'/8444'/0'/0')");
            setText("extPubLabel", "Pool Public Key (m/12381'/8444'/1'/0')");
            setText("pathLabel", "EIP-2333 Derivation Path");
        }
        if (!$("#bip44-tab").hasClass("active") && (cfg.singleTab || !$("#bip32-tab").hasClass("active"))) {
            $("#bip44-tab a").tab("show");
        }
    };

    $("#alt-network").on("change", function() {
        if (current) { netChoice[current] = $(this).val(); }
        recompute();
    });
    $("#alt-role").on("change", function() {
        $("#change-bip44").val($(this).val());
        recompute();
    });

    function cardanoRoot() {
        var phrase = $("#phrase").val().trim(), pass = $("#passphrase").val();
        var key = phrase + "\u0000" + pass;
        if (rootCache.key !== key) {
            rootCache = { key: key, value: null, error: null };
            try { rootCache.value = wasm_bindgen.cardano_root(phrase, pass); }
            catch (e) { rootCache.error = errText(e); }
        }
        if (rootCache.error) { throw new Error(rootCache.error.replace(/^Error: /, "")); }
        return rootCache.value;
    }
    function account() { return parseInt($("#account-bip44").val(), 10) || 0; }
    function selectedRole() { return parseInt($("#alt-role").val(), 10) || 0; }

    // Chia path prefix m/12381/8444/role: every level hardened or none (wallet observer keys)
    function chiaHardened(hardened) { return !!hardened || selectedRole() !== 2; }
    function chiaBase(hardened) {
        var h = chiaHardened(hardened) ? "'" : "";
        return "m/12381" + h + "/8444" + h + "/" + selectedRole() + h;
    }
    function hardenedChecked() { return $(".hardened-addresses").prop("checked"); }

    function chiaAfterDisplay() {
        var seedHex = $("#seed").val().trim();
        $("#bip44-path").val(chiaBase(hardenedChecked()));
        try {
            var k = JSON.parse(wasm_bindgen.chia_keys(seedHex));
            $("#root-key").val(k.masterSk);
            $("#account-xprv-bip44").val(k.fingerprint);
            $("#account-xpub-bip44").val(k.masterPk);
            $("#extended-priv-key").val(k.farmerPk);
            $("#extended-pub-key").val(k.poolPk);
        } catch (e) {
            var msg = errText(e);
            $("#root-key, #account-xprv-bip44, #account-xpub-bip44, #extended-priv-key, #extended-pub-key").val(msg);
        }
    }

    window.altAfterDisplay = function() {
        if (!ready) { return; }
        if (current === "chia") { chiaAfterDisplay(); return; }
        if (current !== "cardano") { return; }
        try {
            var k = JSON.parse(wasm_bindgen.cardano_keys(cardanoRoot(), account(), selectedRole()));
            $("#root-key").val(k.rootXsk);
            $("#account-xprv-bip44").val(k.accountXsk);
            $("#account-xpub-bip44").val(k.accountXvk);
            $("#extended-priv-key").val(k.roleXskHex);
            $("#extended-pub-key").val(k.roleXvkHex);
        } catch (e) {
            var msg = errText(e);
            $("#root-key, #account-xprv-bip44, #account-xpub-bip44, #extended-priv-key, #extended-pub-key").val(msg);
        }
    };

    window.altRow = function(index, hardened) {
        if (!current) { return null; }
        var bip44 = $("#bip44-tab").hasClass("active");
        var base = bip44 ? $("#bip44-path").val() : $("#bip32-path").val();
        if (current === "chia") { base = chiaBase(hardened); hardened = chiaHardened(hardened); }
        var path = base.replace(/\/$/, "") + "/" + index + (hardened ? "'" : "");
        var row = { path: path, address: "", publicKey: "", privateKey: "" };
        if (!ready) { row.address = "WASM module still loading"; return row; }
        var net = netChoice[current];
        try {
            var r;
            if (current === "midnight") {
                var role = selectedRole();
                var parts = path.split("/");
                if (!bip44 && parts.length >= 5 && /^[0-4]$/.test(parts[4])) { role = parseInt(parts[4], 10); }
                r = JSON.parse(wasm_bindgen.midnight_row($("#seed").val().trim(), net, path, role));
            } else if (current === "chia") {
                r = JSON.parse(wasm_bindgen.chia_row($("#seed").val().trim(), net, selectedRole(), index, hardened));
            } else {
                r = JSON.parse(wasm_bindgen.cardano_row(cardanoRoot(), net, account(), selectedRole(), index, !!hardened));
            }
            row.address = r.address; row.publicKey = r.publicKey; row.privateKey = r.privateKey;
        } catch (e) {
            row.address = errText(e);
        }
        return row;
    };
})();
'''

inject = ("<script>\nvar MIDNIGHT_WASM_B64 = \"%s\";\n</script>\n<script>\n%s\n</script>\n<script>%s</script>\n"
          % (wasm_b64, glue, CONTROLLER))
pos = html.rindex("</body>")
html = html[:pos] + inject + html[pos:]
html = replace_once(html, "<title>BIP39 - Mnemonic Code", "<title>BIP39 - Mnemonic Code (Cardano + Midnight + Chia)")

open(out, "w", encoding="utf-8").write(html)
print("wrote", out)
