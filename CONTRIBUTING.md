# Git Flow 工作流

本仓库使用 Git Flow。`main` 和 `develop` 都不接受直接提交，所有改动必须在独立分支完成并通过合并进入目标分支。

## 长期分支

- `main`：稳定发布分支，只接收 release 和 hotfix 合并。
- `develop`：日常集成分支，只接收 feature 和修复分支合并。

建议在 GitHub 为 `main` 和 `develop` 开启分支保护，至少要求 Pull Request 和通过测试后才能合并。

## 功能开发

从最新 `develop` 创建 feature 分支：

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/<short-name>
```

提交并推送：

```bash
git add <files>
git commit -m "feat(scope): summary"
git push -u origin feature/<short-name>
```

然后创建 Pull Request：

```text
feature/<short-name> -> develop
```

本次控制面开发分支为：

```text
feature/control-plane
```

## 发布流程

从 `develop` 创建 release 分支：

```bash
git switch develop
git switch -c release/<version>
```

完成版本检查后，将 release 分支合并到 `main`，打版本标签，再合并回 `develop`。

```text
release/<version> -> main
release/<version> -> develop
```

## 紧急修复

从 `main` 创建 hotfix 分支：

```bash
git switch main
git switch -c hotfix/<short-name>
```

修复完成后同时合并到 `main` 和 `develop`：

```text
hotfix/<short-name> -> main
hotfix/<short-name> -> develop
```

## Commit 约定

使用简洁的 Conventional Commit 风格：

```text
feat(scope): add behavior
fix(scope): correct behavior
refactor(scope): reorganize without behavior changes
test(scope): add or adjust tests
docs: update documentation
chore: maintain tooling or metadata
```

每个 commit 应满足：

- 只处理一个明确目标。
- 可以独立审查和回滚。
- 不混入无关格式化或生成文件。
- 提交前运行单元测试和 Python 编译检查。

## 合并要求

合并到 `develop` 前至少执行：

```bash
python -m unittest discover -s tests -v
python -m compileall -q auto_fill.py autowal
```

仓库默认不提交 `.venv/`、`__pycache__/`、调试截图和本地浏览器驱动。
