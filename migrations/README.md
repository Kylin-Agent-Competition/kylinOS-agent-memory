# Migrations

## 模块定位

SQLite 数据库 schema 版本化迁移管理（Alembic + SQLAlchemy 2.0 Core）。所有结构化记忆表结构的变更必须通过本目录中的迁移脚本执行。

## 输入与输出

- **输入**：当前数据库版本与目标版本
- **输出**：迁移后的数据库 schema

## 责任轨道

- **主要**：D
- **审查**：E

## 当前状态

**D4D：Alembic 工具链 + 基线迁移已建立**（`alembic.ini` / `env.py` / `versions/001_initial_schema.py`）。
生产迁移命令：

```bash
# 升级到最新
alembic upgrade head

# 回滚到基线（每个迁移含 downgrade，FR-DB-002）
alembic downgrade base

# 查看当前版本
alembic current
```

## 迁移目录（ADR-007 命名裁定）

```
migrations/
├── alembic.ini
├── env.py                     # 从 KYLIN_MEMORY_DB / 默认路径读取数据库 URL
└── versions/
    ├── 001_initial_schema.py  # 基线迁移（固定命名，不得改为日期前缀）
    └── YYYYMMDD_<description>.py  # 后续迁移（日期 + 描述）
```

## 约束（冻结）

- 基线迁移固定为 `001_initial_schema.py`；后续迁移使用 `YYYYMMDD_<description>.py`，二者不混用（ADR-007）。
- 每个迁移必须有 `downgrade()`（FR-DB-002）。
- 禁止：手动改 SQLite、`render_as_batch=False` 的 autogenerate、删除列（用重命名迁移）。
- 数据库 URL 不写入 alembic.ini（由 env.py 动态读取配置）。

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | 迁移脚本语法检查、正向/回滚测试（`alembic upgrade head` → `downgrade base`） |
| **L2** | 麒麟 VM 中完整迁移链路测试（`.schema` 与冻结文档逐列对照） |
