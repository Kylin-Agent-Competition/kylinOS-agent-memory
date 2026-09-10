# D15D blocker remediation paths

Run ID: `20260910T142417Z`

## Current status

D15D final lock is blocked by two independent gates:

1. C8 package identity closure.
2. C10 runtime/model contract closure.

No version manifest, submission bundle, PR, or E sign-off may be produced until
both are resolved.

## C8 - original frozen package

The authoritative original identity is:

- Tar SHA-256:
  `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`
- Manifest SHA-256:
  `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0`
- `SHA256SUMS` SHA-256:
  `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67`

The original tar bytes are not available locally. The D14D handoff records that
the current VM and r1 parent snapshot were searched without success. The local
rebuilt tar has a different tar hash, manifest hash, and `source_commit`, so it
is not eligible.

### Acceptable unblock paths

1. Provide the original frozen tar bytes and verify:
   - tar SHA-256 equals `2222c904...`;
   - `package_manifest.json` SHA-256 equals `76a839...`;
   - `package_SHA256SUMS.txt` SHA-256 equals `8540cd...`;
   - `sha256sum -c SHA256SUMS` passes.
2. Obtain explicit human authorization to create a new package from
   `ba3b50e1bdeea185bca9daee9d1d45958f62a636`, then rebuild and rerun the full
   consistency chain. Because the package identity changes, D14D L3 evidence
   must be treated as not directly reusable for the new tar unless a separate
   authorized equivalence record proves otherwise.

The provenance-labeled rebuild alone is not sufficient.

## C10 - runtime/model contract identity

D14D G0 recorded:

| Component | Version | SHA-256 |
|---|---|---|
| SDK | `1.2.0.0-0k0.4` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| Runtime | `1.2.0.4-0k0.1` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| Model | `1.0.0.1-0k0.9` | `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` |

`docs/day14/00_d14a_release_package_contract.md` section 6bis remains
`HANDOFF_REQUIRED` on refreshed remote main. D15D cannot upgrade the frozen
contract or declare closure by itself.

### Acceptable unblock path

Obtain D Reviewer authorization to upgrade contract section 6bis using the D14D
G0 identities above, or otherwise obtain a formal D Reviewer closure record.
After that, D15D may consume the closed identity in the version manifest.
