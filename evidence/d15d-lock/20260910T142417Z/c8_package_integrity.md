# D15D C8 original package integrity

Run ID: `20260910T142417Z`

## Result

`PASS_WITH_ENV_NOTE` for C8 package integrity. The note is limited to WSL's
inability to hash dangling symlinks; it is not a package-byte mismatch and not
Kylin VM evidence.

## Identity

Original tar path:

`C:\Users\jackb\AppData\Local\Temp\kylin-memory-a-d14a-0.1.0-d14a-ba3b50e.tar.gz`

Command:

```powershell
Get-FileHash -Algorithm SHA256 'C:\Users\jackb\AppData\Local\Temp\kylin-memory-a-d14a-0.1.0-d14a-ba3b50e.tar.gz'
```

Result:

```text
2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401
Size: 21,149,791 bytes
```

This matches the frozen D14A tar identity exactly.

Extracted directory:

`E:\Kylin-memory-dev\tmp\d15d-c8-20260910T142417Z\kylin-memory-a-d14a-0.1.0-d14a`

| Object | SHA-256 | Result |
|---|---|---|
| `manifest.json` | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` | PASS |
| `SHA256SUMS` | `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` | PASS |

The package manifest records:

- `package_name = kylin-memory-a-d14a`
- `package_version = 0.1.0-d14a`
- `source_commit = ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- file entries = 3360
- `SHA256SUMS` lines = 3360

## Checksum run

Command executed in WSL:

```bash
cd /mnt/e/Kylin-memory-dev/tmp/d15d-c8-20260910T142417Z/kylin-memory-a-d14a-0.1.0-d14a && sha256sum -c SHA256SUMS
```

Observed result:

```text
exit code: 1
OK: 3357
FAILED open or read: 3
sha256sum: WARNING: 3 listed files could not be read
```

The tar itself contains these symlinks:

```text
runtime/python/bin/python    -> python3.12
runtime/python/bin/python3   -> python3.12
runtime/python/bin/python3.12 -> /usr/bin/python3.12
```

The three failures are because the WSL host does not have
`/usr/bin/python3.12`, so the last link is dangling and cannot be hashed. All
3357 regular listed files returned `OK`. No regular-file hash mismatch was
observed. The original tar was not rebuilt or modified.

## Evidence classification

This is local C8 byte/manifest consistency evidence only. It does not replace
the Kylin VM L3 evidence in D14D and does not upgrade `release_ready` or
`production_ready`.
