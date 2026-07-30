# D1-B-01 Vector Engine 基线边界记录

- 任务：Vector Engine 服务、Collection、CRUD、过滤与重启持久化基线
- 分支：`test/B-vector-engine-baseline`
- 对应提交：`05845a6426e670f34449225f3996f92b90a88ad2`
- 环境：Kylin V11，x86_64，内核 `6.6.0-63-generic`
- 审查状态：`gaoyizhe934` 已授权提交，未推送
- 验证结论：`BLOCKED`

## 已通过的检查

1. `kylin-ai-vector-engine.service` 处于 `active/running`。
2. 服务进程实际持有
   `/home/yanmouren778/.local/share/kylin-ai-vector-engine/default.db`。
3. 官方 SDK 源码检出为
   `openkylin/nile-sp2@bed675f418d32c052a6ab4c5c49bae148d90f678`，工作区干净。
4. 已安装客户端运行库为
   `libkysdk-vector-engine-client 1.2.0.0-0k1.1`。
5. 探针使用官方源码头文件和已安装运行库编译成功。
6. 官方客户端创建成功，SDK 数据面连接成功。

## 阻塞结果

服务预加载数据库模式下，首个数据面就绪调用 `ShowCollections`
返回：

```text
code=1002, message=Unexpected error in RPC handling
```

因此 Collection、CRUD、标量过滤、向量检索和重启持久化均未执行。
不得把本次结果标记为功能通过。

## 环境边界调查

- 已安装服务端：
  `kylin-ai-vector-engine 1.2.0.1-0k0.11`
- 系统仓库候选服务端：
  `kylin-ai-vector-engine 1.2.0.1-0k1.0`
- `apt-get -s install --only-upgrade kylin-ai-vector-engine` 显示只升级该服务包，
  不新增或卸载依赖。
- 实际系统升级需要管理员权限，本次未安装或覆盖系统包。
- 候选包包含旧包未提供的
  `/usr/share/kylin-ai-vector-engine/vector_engine.json`。
- 候选服务启动时还会动态加载 `libtcm.so.1`；当前 VM 和候选 DEB
  依赖声明均未提供该模块，候选进程退出码为 `255`。
- 未伪造 `libtcm.so.1`，避免绕过麒麟可信模块安全边界。

## 恢复与影响范围

- 原 `kylin-ai-vector-engine.service` 已恢复为 `active/running`。
- 原默认数据库未覆盖、未删除。
- 测试仅使用唯一 Collection 名 `d1_vector_baseline`；由于
  `ShowCollections` 即失败，未创建该 Collection。
- 未修改其他成员代码，未发现 Git 冲突。
- 未提交，未 Push。

## 解除阻塞条件

由环境管理员提供版本一致且依赖完整的 Vector Engine 服务端，至少满足：

1. 服务端与 `libkysdk-vector-engine-client 1.2.0.0-0k1.1` 协议兼容；
2. 候选服务所需的 `vector_engine.json` 可用；
3. 官方 `libtcm.so.1` 可信模块及包依赖完整；
4. `ShowCollections` 不再返回 RPC `1002`。

解除后按 `prepare -> 人工重启服务 -> verify -> 保存证据 -> cleanup`
顺序重新执行。不得跳过 `prepare` 或将当前阻塞结果当作持久化通过。

## 原始证据

- 文件：`d1-b-vector-engine-boundary-20260730.log`
- SHA-256：
  `b9c947d949917343cfb077f32fac23124a6f9c182650f7fc937112ab47ae2e3d`
