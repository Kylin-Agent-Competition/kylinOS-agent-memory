# D1-B-02 原生 Hybrid/RRF 证据等级核定

- 任务：核对原生 Hybrid/RRF 当前证据等级
- 分支：`test/B-vector-engine-baseline`
- 环境：Kylin V11，x86_64，内核 `6.6.0-63-generic`
- 审查状态：待 `gaoyizhe934` 人工审核，尚未推送
- 最高现有证据：`ABI_VERIFIED / E3`
- 端到端运行状态：`UNTESTED`，不得声明宿主可用

## 核定结论

官方能力矩阵中的 `VEC-005` 原记录为
`SOURCE_VERIFIED / E2`。本次在真实 Kylin 宿主的已安装客户端库中
确认了 `HybridSearch`、`RRFRanker` 和 `WeightedRanker` 导出符号。
按照同一份矩阵的证据定义，客户端能力最高证据可由 E2 升级为：

```text
ABI_VERIFIED / E3
```

该升级只证明当前宿主安装的客户端二进制具备对应 ABI。服务端是否接受
HybridSearch 请求、RRF 结果是否正确、异常与重启后是否稳定，均没有
E4/E5 证据。因此不得把本次核定写成“原生 Hybrid/RRF 已支持”。

## 证据等级依据

官方矩阵给出的相关定义为：

| 等级 | 证据来源 | 本次对应结果 |
|---|---|---|
| E1 | 官方说明、头文件、包元数据 | 头文件声明 `HybridSearch` 与 Ranker |
| E2 | 源码静态分析 | 请求构造、Ranker 序列化与 gRPC 转发路径存在 |
| E3 | 真实宿主 ABI、依赖、配置或数据库 Schema | 已安装 `.so` 导出 Hybrid/RRF 符号 |
| E4 | 银河麒麟宿主成功运行 | 未取得 |
| E5 | 多场景、异常、服务/系统重启回归 | 未取得 |

## E2：官方 SDK 静态路径

核验源码：

```text
openkylin/nile-sp2
bed675f418d32c052a6ab4c5c49bae148d90f678
```

工作区干净。已定位：

1. `Database.h:150-154` 声明 `HybridSearch`。
2. `Ranker.h:34-48` 声明 `RRFRanker` 与 `WeightedRanker`。
3. `Ranker.cpp:28-49` 将策略编码为 `rrf` 或 `weighted`，并序列化
   `k` 或 `weights` 参数。
4. `MilvusClientImpl.cpp:431-605` 校验 Collection 与向量字段、构建
   `HybridSearchRequest`、写入 Ranker 参数并交给连接层。
5. `MilvusConnection.cpp:136-138` 将请求转发到 gRPC
   `Stub::HybridSearch`。
6. 官方 Demo 同时构造稠密/稀疏检索请求，以 `RRFRanker` 调用
   `HybridSearch`；CMake 中存在 `client-hybrid` 和
   `client-dynamic-hybrid` 目标。

以上只构成 `SOURCE_VERIFIED / E2`。

## E3：真实安装客户端 ABI

宿主安装包：

```text
libkysdk-vector-engine-client:amd64  1.2.0.0-0k1.1
```

实际库文件：

```text
/usr/lib/x86_64-linux-gnu/libkysdk-vector-engine-client.so.0.0.1
SHA-256 14cce29888cdd1fb086f6e8433dd69718656f68548e3bdb4287ec157d626cbc6
```

`nm -D -C` 确认导出：

- `VectorDB::MilvusClientImpl::HybridSearch(...)`
- `VectorDB::MilvusConnection::HybridSearch(...)`
- `VectorDB::RRFRanker` 构造函数、`GetStrategy`、`GetParams`
- `VectorDB::WeightedRanker` 构造函数、`GetStrategy`、`GetParams`

这满足矩阵对 E3“真实宿主 ABI”的定义，故最高证据为
`ABI_VERIFIED / E3`。

## E4 未成立的原因

已提交的 `D1-B-01` 运行边界证据显示，当前服务在首个数据面就绪调用
`ShowCollections` 时返回：

```text
code=1002, message=Unexpected error in RPC handling
```

同时，官方 SDK 的 `HybridSearch` 在发起 RPC 前会先执行
`DescribeCollection` 与向量字段校验。Collection 数据面尚不可用时，
无法构造一条有效的原生 Hybrid/RRF 端到端成功证据。

因此本次没有绕过前置条件、没有伪造 Collection，也没有把 ABI 存在
误写为功能通过。

## 对项目路线的影响

- 客户端最高证据：由矩阵原 `SOURCE_VERIFIED / E2` 更新为
  `ABI_VERIFIED / E3`。
- 原生 Hybrid/RRF 端到端：保持 `UNTESTED`，属于 P2 条件范围。
- 默认产品路径：仍为应用层 RRF，不因本次 ABI 发现而改变。
- 后续若要升级为 E4，必须在 Vector Engine 数据面解除 RPC `1002`
  阻塞后，以真实 Collection、稠密/稀疏请求和结果正确性断言实测。

## 修改与冲突说明

- 本节点只新增证据记录和索引，不修改生产代码。
- 未重启服务，未写入或删除 VM 数据。
- 未修改其他成员代码，未发现 Git 冲突。
- 官方矩阵的 E2 记录与本次 E3 结论属于证据升级，不是代码冲突；
  历史 E2 结论保留，不覆盖或删除。

## 原始证据

- 文件：`d1-b-native-hybrid-rrf-evidence-20260731.log`
- SHA-256：`871114c58101f20e0de8f64e0ab97bf0a6eb75099cdeb0fbb66587768dde4197`
