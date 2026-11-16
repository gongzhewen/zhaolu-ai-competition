from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path(r'D:\Backup\Documents\ChatGPT\Desktop')
STAGE_ROOT = ROOT / 'competition-submission-stage'
PACKAGE = STAGE_ROOT / 'zhaolu-ai-2026-competition-submission'
ZIP_PATH = ROOT / 'zhaolu-ai-2026-competition-submission.zip'

IGNORE_DIRS = {
    '.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache',
    'storage', 'data', 'backups', 'zhaolu_ai_v2.egg-info', '.idea', '.vscode',
}
IGNORE_FILES = {'.env', '.env.baota', '.env.docker', '.env.mysql'}
IGNORE_SUFFIXES = {'.pyc', '.pyo', '.log'}


def ignore(_dir: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name in IGNORE_DIRS or name in IGNORE_FILES or Path(name).suffix in IGNORE_SUFFIXES
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + '\n', encoding='utf-8')


def build() -> None:
    if STAGE_ROOT.exists():
        resolved = STAGE_ROOT.resolve()
        if ROOT.resolve() not in resolved.parents:
            raise RuntimeError(f'unsafe staging path: {resolved}')
        shutil.rmtree(STAGE_ROOT)
    PACKAGE.mkdir(parents=True)

    # 01 Report
    report_dir = PACKAGE / '01_作品方案'
    report_dir.mkdir(parents=True)
    shutil.copy2(DESKTOP / '2026AIC-算法创新赛-作品方案-修订版.docx', report_dir / '2026AIC-算法创新赛-作品方案-修订版.docx')
    shutil.copy2(DESKTOP / '2026AIC-算法创新赛-作品方案-修订版.pdf', report_dir / '2026AIC-算法创新赛-作品方案-修订版.pdf')

    # 02 Source
    source = PACKAGE / '02_软件源码'
    source.mkdir(parents=True)
    for name in ['apps', 'packages', 'scripts', 'tests', 'deploy', 'infra']:
        src = ROOT / name
        if src.exists():
            shutil.copytree(src, source / name, ignore=ignore)
    for name in [
        '.dockerignore', '.env.baota.example', '.env.docker.example', '.gitignore',
        'docker-compose.baota.yml', 'docker-compose.yml', 'pyproject.toml', 'README.md',
    ]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, source / name)

    # 03 Documentation
    docs = PACKAGE / '03_说明文档'
    docs.mkdir(parents=True)
    selected_docs = [
        'v1-postgres-to-v2-mysql-sync.md', 'full-api-audit.md', 'data-consistency-audit.md',
        'mysql-regression.md', 'deployment-guide.md', 'baota-docker-nginx-deployment.md',
        'docker-nginx-deployment.md', 'baota-update-full-workflow.md', '2c4g-optimization.md',
        'mobile-compatibility.md', 'tool-migration.md', 'agent-parity.md',
        'domain-ssl-complete-checklist.md',
    ]
    for name in selected_docs:
        src = ROOT / 'docs' / name
        if src.exists():
            shutil.copy2(src, docs / name)

    write(docs / '01_软件说明.md', '''
# 招录智策软件说明

## 产品定位

招录智策是面向高校招生管理部门、校级管理者和数据治理人员的 AI 数据分析与决策辅助软件。系统把数据导入、质量治理、招生分析、自然语言问数、异常预警、趋势预测、计划沙盘、学生管理、报告和审计整合在同一产品中。

## 技术架构

- 前端：React 19 + Vite 6 + TypeScript + Ant Design + ECharts
- 后端：FastAPI + Pydantic v2 + SQLAlchemy Async
- 数据库：MySQL 8.0、InnoDB、utf8mb4、JSON
- 会话缓存：进程内 L1 缓存，Redis 为可选 Full 能力
- 智能体：Agent Core + 规则路由 + 14 个受控工具
- 可选模型：MiniMind 本地路由
- 汇总分析：MySQL 汇总分析表 + 一致性自愈
- 知识检索：关键词、短语、字符 n-gram；向量检索为后续扩展

## 页面与功能

系统包含登录、驾驶舱、招生总览、招生计划、生源总览、数据导入、DBF 导入、数据质量、专业别名、AI 助手、AI 洞察、异常检测、计划沙盘、预测、报告、用户、角色、学生和审计等页面。

## 智能体工具

系统保留 14 个受控工具：招生总览、生源总览、考生画像、单科成绩、专业志愿、体检摘要、预测、官方招生统计、专业别名、学生档案、学生条件统计、异常检测、计划沙盘和政策问答。

## 安全边界

- 模型只负责理解、规划和解释，不直接计算业务数字。
- 学生姓名、证件号、手机号和地址不进入外部模型和长期记忆。
- 学生档案和学生条件统计只返回权限允许的结果。
- 重要操作写入审计日志。
''')

    write(docs / '02_核心算法说明.md', '''
# 核心算法说明

## 1. 数据先行智能体

用户问题先经过学校上下文、规则路由、工具规划和参数抽取，业务数字由 14 个受控工具从 MySQL 查询或确定性计算，模型不能直接执行 SQL，也不能自由生成业务数字。

## 2. 规则优先与可选模型分级

默认链路使用规则和模板处理明确的年份、省份、专业、成绩、姓名和统计条件。启用 MiniMind 后用于口语化和复杂问法路由；未启用时自动回退规则路由。任何模型输出都经过工具白名单、参数类型、参数来源和风险校验。

## 3. 专业名称跨省归一

系统保存来源专业名称、来源键、省份范围和标准专业 ID。查询和汇总分析表使用标准专业名，人工修改后会更新缓存并重建汇总分析表。

## 4. 预测、异常与沙盘

- 预测：使用历年招生计划、录取人数和完成率拟合线性趋势，输出预测值与波动区间。
- 异常：检测计划或录取为零、完成率偏低、志愿热度异常、同比波动和计划缺口。
- 沙盘：根据志愿热度计算需求弹性，模拟扩招或缩招后的预计录取、完成率和风险等级。

## 5. 数据支撑与自查

回答依据由工具结果、数据来源、可验证指标、知识引用和数字一致性共同约束。数据支撑度低于阈值时统一拒答。回答生成后执行数据依据、数字一致性、任务完整性、安全和引用质量检查。

## 6. 记忆与反馈

长期记忆保存用户偏好、非敏感事实和对话摘要，不保存学生 PII。反馈优化只更新回答模板权重，不修改基础模型。

## 7. MySQL 兼容与汇总自愈

SQL 兼容层处理 PostgreSQL 与 MySQL 在 Schema、JSON、RETURNING、ON CONFLICT、窗口函数和聚合语法上的差异。分析前会检查基础计划表与汇总分析表是否一致，不一致时自动刷新汇总、结束旧事务快照并重新查询。
''')

    write(docs / '03_测试报告.md', '''
# 测试报告

## 测试范围

覆盖认证、招生分析、预测、异常、计划沙盘、专业别名、学生管理、用户角色、数据质量、Excel/CSV 导入、DBF 导入、报告、审计、AI 助手和流式接口。

## 自动化结果

```text
OpenAPI 操作：81 个全部通过
pytest：50 passed
AI 工具回归：14/14
前端生产构建：通过
MySQL 兼容索引：46/46 已存在
数据一致性：通过
汇总自愈故障注入：通过
DOCX/PDF 报告生成：通过
```

## 数据一致性

```text
学生身份：28450
招生计划：5120
科目成绩：312950
专业志愿：142423
学生跟进：28450
报到状态：28450
体检摘要：23250
```

基础计划与汇总分析表逐年一致，计划孤立维度、录取汇总孤立计划、学生关联孤立记录和知识切片孤立记录均为 0。

## 复现命令

```powershell
.\.venv\\Scripts\\python.exe -m pytest -q
.\.venv\\Scripts\\python.exe scripts\\mysql\\verify_regression.py
.\.venv\\Scripts\\python.exe scripts\\mysql\\verify_data_consistency.py
.\.venv\\Scripts\\python.exe scripts\\mysql\\verify_rollup_self_heal.py
```
''')

    write(docs / '04_部署指南.md', '''
# 部署指南

## 运行环境

- Ubuntu 22.04/24.04 或 Windows
- Docker 与 Docker Compose，或原生 MySQL 8.0 + Python 3.10+
- Nginx 或宝塔面板反向代理
- 可选：Redis、MiniMind 本地模型接口

## Docker 部署

```bash
cp .env.docker.example .env.docker
docker compose -f docker-compose.yml up -d --build
```

浏览器访问 `http://127.0.0.1:8080`。默认账号为 `admin / ChangeMe123!`。

## 宝塔部署

宝塔 Nginx 监听 80/443，反向代理到 Docker web 容器的 `127.0.0.1:8080`。MySQL、FastAPI 和 Redis 不直接暴露公网。

## 演示数据导入

正确数据文件为：

```text
04_演示数据/zhaolu-v2-demo-synced-20261003-191749.sql.zip
```

解压后导入 Docker MySQL：

```bash
docker compose -p zhaolu-ai-v2 --env-file .env.baota -f docker-compose.baota.yml exec -T mysql \\
  sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root --default-character-set=utf8mb4' \\
  < zhaolu-v2-demo-synced-20261003-191749.sql
```

导入前先备份现有 MySQL。不要使用 `down -v`，不要把 `DEMO_FORCE_RESET` 设为 `1`。

## 模型配置

默认演示不需要外部模型。需要复杂语义规划时，在环境文件中配置 MiniMind 本地模型服务；未配置时自动回退规则路由和确定性工具。
''')

    write(docs / '05_数据与迁移说明.md', '''
# 数据与迁移说明

## 正确数据源

提交包中的演示数据来自 v1 PostgreSQL 的 `zhaolu_demo` 模拟库，不包含正式录取数据。

## 模拟数据规模

```text
学生身份：28450
学生档案：28450
录取明细：28450
招生计划：5120
录取汇总：5120
科目成绩：312950
专业志愿：142423
学生跟进：28450
报到状态：28450
体检摘要：23250
专业别名：14
```

## PostgreSQL 到 MySQL 转换

迁移器处理 Schema 映射、JSONB 到 JSON、vector 与数组到 JSON、timestamptz 时区转换、布尔值、数值类型和 UUID。原主键 ID 保留，迁移后重置自增序列，并刷新汇总分析表。

## 运行保护

`seed_mysql_demo.py` 检测到已有招生计划、学生或录取记录时自动跳过重置；只有 `DEMO_FORCE_RESET=1` 才会清库重灌。
''')

    write(docs / '06_提交文件清单.md', '''
# 提交文件清单

- `01_作品方案`：修订版作品方案 DOCX 和校验 PDF。
- `02_软件源码`：FastAPI 后端、React/Vite 前端、Agent Core、测试、迁移脚本、Docker 与 Nginx 配置。
- `03_说明文档`：软件说明、核心算法、测试报告、部署指南、数据迁移说明及参考文档。
- `04_演示数据`：仅包含 `zhaolu_demo` 模拟数据的 MySQL 备份。
- `05_校验`：文件清单和 SHA256 校验值。
''')

    # 04 Demo data
    demo = PACKAGE / '04_演示数据'
    demo.mkdir(parents=True)
    demo_zip = ROOT / 'backups' / 'zhaolu-v2-demo-synced-20261003-191749.sql.zip'
    demo_sha = ROOT / 'backups' / 'zhaolu-v2-demo-synced-20261003-191749.sql.zip.sha256'
    if not demo_zip.exists():
        raise FileNotFoundError(demo_zip)
    shutil.copy2(demo_zip, demo / demo_zip.name)
    if demo_sha.exists():
        shutil.copy2(demo_sha, demo / demo_sha.name)

    # 05 Manifest and hashes
    verify = PACKAGE / '05_校验'
    verify.mkdir(parents=True)
    files = sorted(path for path in PACKAGE.rglob('*') if path.is_file())
    manifest = ['# 提交包文件清单', '']
    hashes = []
    for path in files:
        rel = path.relative_to(PACKAGE).as_posix()
        manifest.append(f'- `{rel}` ({path.stat().st_size} bytes)')
        hashes.append(f'{sha256(path)}  {rel}')
    write(verify / 'PACKAGE_MANIFEST.md', '\n'.join(manifest))
    write(verify / 'SHA256SUMS.txt', '\n'.join(hashes))

    # Root guide
    write(PACKAGE / 'README.md', '''
# 招录智策提交包

本包用于 2026 第八届全球校园人工智能算法精英大赛算法创新赛提交。

## 目录

```text
01_作品方案
02_软件源码
03_说明文档
04_演示数据
05_校验
```

## 快速验证

1. 解压 `04_演示数据` 中的 MySQL 备份。
2. 按 `03_说明文档/04_部署指南.md` 启动 MySQL、后端和前端。
3. 登录 `admin / ChangeMe123!`。
4. 打开 AI 助手，提问“2025年各专业招生计划完成情况怎么样？”。
5. 预计返回 2025 年模拟计划 6000 人、录取 5957 人。

## 默认运行策略

默认运行不依赖外部大模型，规则路由和受控工具即可完成常见数据问答。MiniMind 和 Redis 为可选增强能力。
''')

    # Create final ZIP without including the hash file itself.
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(PACKAGE.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(STAGE_ROOT).as_posix())

    package_hash = sha256(ZIP_PATH)
    (ZIP_PATH.with_suffix('.zip.sha256')).write_text(
        f'{package_hash}  {ZIP_PATH.name}\n', encoding='ascii'
    )
    print(f'package={ZIP_PATH}')
    print(f'size={ZIP_PATH.stat().st_size}')
    print(f'sha256={package_hash}')


if __name__ == '__main__':
    build()
