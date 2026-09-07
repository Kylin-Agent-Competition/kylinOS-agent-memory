# D12D AGT-006 Kaiming 5.0.3 Reverification

- Task: `TD-DEPLOY-001` / AGT-006
- Evidence level: Kylin VM L2
- Evidence source: `evidence/l2-kylin-vm/d12d_agt006_kaiming_503_deploy_noninterference_20260904.log`
- Tested VM tree: `b70827c5e9c9e014ae2c025eb01d0adfaabd4ef9`
- Main deployment-artifact equivalence: `cc4acf6` and `b70827c` resolve to the identical Git blobs for `packaging/systemd/install_kylin_memory.sh` (`be239e0...`) and `packaging/systemd/kylin-memory.service` (`39612b...`).
- Recovery snapshot: `d12d-agt006-pre-20260904` / `b353ef16-0620-4881-bbe8-16df8759a88e`

## Verified

1. The actual Kaiming application registration is `cn.kylin.kylin-aiassistant`, module `binary`, version `5.0.3`, at `/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/5.0.3`.
2. `kaiming info` identifies the expected Kaiming runtime; `kaiming ps` shows the assistant container after project deployment lifecycle completion.
3. Project-owned `rollback -> install` completed: rollback made `kylin-memory.service` inactive; reinstall recreated backup assets and ended with the service active and its UDS socket present.
4. The complete official layer file-tree SHA-256 was unchanged before and after the lifecycle: `3d3926c91e94430e187a99efae5edd3a5ea0a5db38aadcd2289169f1a7a78c75`.

## Boundary And Result

This verifies the changed 5.0.3 layout and demonstrates that the current project user-service deployment/rollback does not alter the official assistant layer or remove its running container. It does not modify, inject into, or claim a Hook integration with the official assistant.

`TD-DEPLOY-001` remains `In Progress`. The AGT-006 acceptance set still requires a minimal KySec authorization/ACL proof on the 5.0.3 deployment path. That proof is blocked by the unresolved `TD-KYSEC-001` enforcement verification; the prior broad-policy probe made SSH execution unstable and was rolled back through a VM snapshot. No global KySec setting was changed in this run.
