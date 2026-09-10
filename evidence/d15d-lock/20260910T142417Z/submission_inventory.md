# D15D submission inventory

Run ID: `20260910T142417Z`

## Fixed content list

| # | Artifact | Location / path | Identity / status |
|---|---|---|---|
| 1 | Original frozen package tar | `C:\Users\jackb\AppData\Local\Temp\kylin-memory-a-d14a-0.1.0-d14a-ba3b50e.tar.gz` | tar SHA `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`; size 21,149,791 bytes |
| 2 | Extracted package directory | `E:\Kylin-memory-dev\tmp\d15d-c8-20260910T142417Z\kylin-memory-a-d14a-0.1.0-d14a` | matches tar identity; `manifest.json` SHA `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0`; `SHA256SUMS` SHA `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` |
| 3 | Version manifest | `docs/day15/D15D_VERSION_MANIFEST.json` | `release_commit=ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| 4 | Package contract | `docs/day14/00_d14a_release_package_contract.md` | FROZEN v5, section 6bis G0 identity closed |
| 5 | D14D evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` | 23/23 checksums OK |
| 6 | D15D evidence root | `evidence/d15d-lock/20260910T142417Z` | C1-C12 evidence and checksums |

## Comparison result

The fixed list maps one-to-one to task card section 2.1:

- no missing required artifact;
- no extra package, wheel, Kaiming artifact, production script, or runtime binary;
- the extracted directory is a verification copy of artifact 1, not a separately
  rebuilt package;
- artifact 1 remains outside the Git tree and is not replaced by the
  provenance-labeled rebuild.

This inventory does not declare Reviewer E sign-off, Release Gate completion,
production readiness, or D15E final submission lock.
