# D14C 请求：trusted host identity 正式交接

**请求对象：D 轨。状态：`BLOCKED_PENDING_D_APPROVAL`。**

请提供可被 D14C preflight 消费的书面 approval，而非仅口头确认：

- AI Assistant package/version、binary absolute path、SHA-256、process owner、可接受 cmdline identity；
- Host Chat DB absolute path、owner/permissions、schema reference；
- MemoryClient 与 production resolver identity（路径/version/SHA-256）；
- 独立 trusted identity 的注入位置、threat boundary，及与 payload `user_id` 的 fail-closed 比对在 cache lookup 前执行的证明；
- 适用的 route、tested commit、approval reference 和 identity manifest SHA-256。

不可接受：以 payload 自证、`trusted_identity=None`、test/validation profile 或历史 VM 记录代替批准。收到 approval 前，D14C 的 G5 保持 `BLOCKED`。
