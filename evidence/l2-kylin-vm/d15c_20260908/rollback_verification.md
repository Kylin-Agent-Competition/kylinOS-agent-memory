# Rollback Verification Evidence

| Field | Value |
|-------|-------|
| Evidence ID | EV-004 |
| Task | P1-5 Rollback |
| Status | VERIFIED |
| Date | 2026-09-08 |

## 1. Binary SHA-256 Records

| Binary | SHA-256 | Size |
|--------|---------|------|
| Patched (deployed) | `a712d541496934520092d0688cd2be0e26d7c7cbd2fe254551f0af8dc06a82f0` | 4,135,232 |
| Original (backup) | `86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6` | 4,135,232 |
| Restored (after rollback) | `86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6` | 4,135,232 |

## 2. Deployment Path

```
/var/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant
```

## 3. Rollback Command

```bash
sudo cp ~/d15c/backup/layer-kylin-aiassistant.orig \
  /var/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant
```

## 4. Post-Rollback Verification

- SHA-256 match: `86453fc660a47940...` ✓
- Assistant launched with `QT_QPA_PLATFORM=offscreen kaiming run cn.kylin.kylin-aiassistant`
- Process running: PID 187375, 187390 ✓
- No patched code artifacts remaining (binary restored to original)

## 5. Backup Location

```
~/d15c/backup/layer-kylin-aiassistant.orig  (root:root, 4135232 bytes)
~/d15c/backup/kylin-aiassistant.orig        (bacon:bacon, 4135232 bytes)
~/d15c/backup/msgpane.cpp.step137bak        (source backup)
~/d15c/backup/deploy_manifest.txt           (deployment log)
```
