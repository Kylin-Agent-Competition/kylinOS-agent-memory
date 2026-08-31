# Git 操作规范（不断迭代）

> 本文件记录本项目的 Git 分支命名、提交规范、PR 流程。每次新任务开始前阅读并遵守，有修改直接在本文件上改动。
>
> **开工前同时阅读以下文件**：
> - `docs/project-management/session-handoff-20260820.md` — 会话交接文档（D11，本地未跟踪）
> - `02_麒麟OS_Agent记忆系统_总体架构_团队分工与标准开发SOP_v1.0_20260726.docx` — 总体架构与团队分工
> - `04_麒麟OS_Agent记忆系统_Agent_LLM与CodeAgent使用指南_v1.0_20260726.docx` — Agent/LLM 使用指南
> - `麒麟OS_Agent记忆系统_15天75项个人施工台账_修正版.xlsx` — 75 项施工台账

## 一、分支命名规范

格式：`<type>/<具体实现描述>`

| type | 说明 |
|------|------|
| feat | 新功能 (feature) |
| fix | 修补 bug |
| docs | 文档变更 |
| style | 代码格式（不影响代码运行的变动，如空格、分号） |
| refactor | 重构（既不是新增功能，也不是修改 bug） |
| perf | 性能优化 |
| test | 增加测试 |
| chore | 构建过程或辅助工具的变动 |

示例：`feat/CardManager`、`fix/login-timeout`、`docs/api-spec`

## 二、提交信息规范

格式：`<type>(<scope>)：<描述>`

- type：同上表
- scope：影响范围/模块名（如 CardManager、embedding-cache）
- 描述：中文，简洁说明做了什么

示例：
- `fix(CardManager)：修复了出牌卡住的bug`
- `feat(embedding-cache)：实现按内容指纹的缓存失效接口`
- `docs(git-conventions)：更新分支命名规范`

## 三、原子化提交原则

- 修一个小 bug 就可以提交一次，不要攒个大的
- 每次提交聚焦一个逻辑变更
- 提交后如果发现问题，再提交一个 fix 修复，不要 amend 已有提交
- 这样之后出了问题好回退

## 四、PR 流程

1. **rebase 而非 merge**：提交 PR 前，先在本地 rebase main 分支，解决冲突后再推送
2. **不要直接推 main**：主分支不能直推，必须通过 PR 合并
3. PR 描述使用模板（见 `docs/day10/02_pr_description.md` 格式）
4. 合并前确保 Reviewer 审核通过

## 五、示例

```bash
# 创建分支
git checkout -b feat/CardManager

# 开发过程中的原子提交
git commit -m "feat(CardManager)：实现出牌逻辑"
git commit -m "fix(CardManager)：修复手牌数量显示错误"
git commit -m "test(CardManager)：添加出牌边界测试"

# 提交 PR 前
git fetch origin main
git rebase origin/main
# 解决冲突后
git push --force-with-lease origin feat/CardManager

# 创建 PR
gh pr create --base main --head feat/CardManager ...
```