"""`VectorProvider` 抽象端口（`docs/day3/08` §6）。

本模块只冻结操作语义、输入输出和 deadline，不冻结同步/异步/进程池调度方式，
也不包含真实 SDK、SQLite、FTS5、Collection、Outbox 或 Gateway 实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from retrieval.contracts import (
    IndexState,
    IndexStateRequest,
    ProviderResult,
    VectorCapabilities,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorRebuildRequest,
    VectorRebuildResult,
    VectorSearchRequest,
    VectorSearchResult,
    VectorUpsertRequest,
    VectorUpsertResult,
)


class VectorProvider(ABC):
    """B 轨 `vector-retrieval/v1` 最小可测试端口。

    实现约束（详见 08 §6）：
    - `capabilities()` 是只读操作，不得隐式加载模型、建 Collection、重建或改状态；
    - 写操作必须遵循幂等复合域、payload_hash 复算、用户隔离与水位比较；
    - Search 先做 `user_id` 硬过滤，回源由 Service 最终校验；
    - 跨层使用同一绝对 `deadline_at`，开始新副作用前必须再检查 deadline/取消。
    """

    @abstractmethod
    def capabilities(self) -> VectorCapabilities:
        """返回只读能力描述，不改变任何状态。"""

    @abstractmethod
    def upsert(self, request: VectorUpsertRequest) -> ProviderResult[VectorUpsertResult]:
        """幂等写入一批向量记录。"""

    @abstractmethod
    def search(self, request: VectorSearchRequest) -> ProviderResult[VectorSearchResult]:
        """返回经 `user_id` 硬过滤的召回命中，不含正文。"""

    @abstractmethod
    def delete(self, request: VectorDeleteRequest) -> ProviderResult[VectorDeleteResult]:
        """按已解析、非空、受控的选择器删除索引项。"""

    @abstractmethod
    def rebuild(self, request: VectorRebuildRequest) -> ProviderResult[VectorRebuildResult]:
        """从 SQLite 确定性快照重建新代次，失败不得替换当前可用代次。"""

    @abstractmethod
    def get_index_state(self, request: IndexStateRequest) -> ProviderResult[IndexState]:
        """严格只读返回 `IndexState`，不得产生状态转换。"""