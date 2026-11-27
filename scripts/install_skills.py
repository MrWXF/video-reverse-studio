#!/usr/bin/env python3
"""
Skills 安装脚本
从 gstack 和 hermes-agent 安装热门 skills 到 .claude/skills 目录
"""

import os
import shutil
import subprocess
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"

# Skills 来源路径
GSTACK_PATH = Path("D:/project/github/gstack")
HERMES_PATH = Path("D:/project/github/hermes-agent/optional-skills")
CODEX_PATH = Path("C:/Users/Administrator/.codex/skills/.system")

# 分类定义
CATEGORIES = {
    "01-discovery-and-design": {
        "name": "需求发现与设计",
        "skills": {
            "office-hours": {"source": "gstack", "level": "S"},
            "plan-design-review": {"source": "gstack", "level": "S"},
            "design-review": {"source": "gstack", "level": "S"},
            "plan-ceo-review": {"source": "gstack", "level": "A"},
            "design-consultation": {"source": "gstack", "level": "A"},
            "design-shotgun": {"source": "gstack", "level": "A"},
            "design-html": {"source": "gstack", "level": "A"},
            "adversarial-ux-test": {"source": "hermes", "level": "A", "subpath": "dogfood"},
            "concept-diagrams": {"source": "hermes", "level": "B", "subpath": "creative"},
        }
    },
    "02-architecture-planning": {
        "name": "架构与规划",
        "skills": {
            "spec": {"source": "gstack", "level": "S"},
            "plan-eng-review": {"source": "gstack", "level": "S"},
            "plan-devex-review": {"source": "gstack", "level": "A"},
            "context-save": {"source": "gstack", "level": "A"},
            "context-restore": {"source": "gstack", "level": "A"},
            "autoplan": {"source": "gstack", "level": "B"},
        }
    },
    "03-development": {
        "name": "开发与生成",
        "skills": {
            "review-agent": {"source": "codex", "level": "S"},
            "skill-creator": {"source": "codex", "level": "S"},
            "skill-installer": {"source": "codex", "level": "S"},
            "careful": {"source": "gstack", "level": "A"},
            "guard": {"source": "gstack", "level": "A"},
            "freeze": {"source": "gstack", "level": "A"},
            "docker-management": {"source": "hermes", "level": "A", "subpath": "devops"},
            "fastmcp": {"source": "hermes", "level": "A", "subpath": "mcp"},
            "codex": {"source": "gstack", "level": "A"},
            "mcporter": {"source": "hermes", "level": "B", "subpath": "mcp"},
            "page-agent": {"source": "hermes", "level": "B", "subpath": "web-development"},
        }
    },
    "04-testing-security": {
        "name": "测试与安全",
        "skills": {
            "qa-only": {"source": "gstack", "level": "S"},
            "qa": {"source": "gstack", "level": "S"},
            "browse": {"source": "gstack", "level": "S"},
            "cso": {"source": "gstack", "level": "S"},
            "review": {"source": "gstack", "level": "S"},
            "benchmark": {"source": "gstack", "level": "A"},
            "1password": {"source": "hermes", "level": "A", "subpath": "security"},
            "oss-forensics": {"source": "hermes", "level": "B", "subpath": "security"},
        }
    },
    "05-deployment": {
        "name": "发布与部署",
        "skills": {
            "ship": {"source": "gstack", "level": "S"},
            "setup-deploy": {"source": "gstack", "level": "S"},
            "land-and-deploy": {"source": "gstack", "level": "S"},
            "canary": {"source": "gstack", "level": "S"},
            "document-release": {"source": "gstack", "level": "A"},
            "landing-report": {"source": "gstack", "level": "B"},
        }
    },
    "06-operations": {
        "name": "运维与维护",
        "skills": {
            "investigate": {"source": "gstack", "level": "S"},
            "health": {"source": "gstack", "level": "S"},
            "document-generate": {"source": "gstack", "level": "S"},
            "retro": {"source": "gstack", "level": "A"},
            "learn": {"source": "gstack", "level": "A"},
        }
    },
    "07-integrations": {
        "name": "AI媒体与集成",
        "skills": {
            "imagegen": {"source": "codex", "level": "A"},
            "whisper": {"source": "hermes", "level": "A", "subpath": "mlops"},
            "inference-sh-cli": {"source": "hermes", "level": "A", "subpath": "devops", "skill_dir": "cli"},
            "duckduckgo-search": {"source": "hermes", "level": "A", "subpath": "research"},
            "stable-diffusion": {"source": "hermes", "level": "B", "subpath": "mlops"},
            "parallel-cli": {"source": "hermes", "level": "B", "subpath": "research"},
            "qmd": {"source": "hermes", "level": "B", "subpath": "research"},
            "scrapling": {"source": "hermes", "level": "B", "subpath": "research"},
        }
    }
}

def get_source_path(source: str, skill_name: str, subpath: str = None, skill_dir: str = None) -> Path:
    """获取 skill 的源路径"""
    if source == "gstack":
        return GSTACK_PATH / skill_name
    elif source == "hermes":
        dir_name = skill_dir if skill_dir else skill_name
        if subpath:
            return HERMES_PATH / subpath / dir_name
        return HERMES_PATH / dir_name
    elif source == "codex":
        return CODEX_PATH / skill_name
    return None

def install_skill(skill_name: str, skill_info: dict, category_dir: Path) -> bool:
    """安装单个 skill"""
    source = skill_info["source"]
    subpath = skill_info.get("subpath")
    skill_dir = skill_info.get("skill_dir")

    source_path = get_source_path(source, skill_name, subpath, skill_dir)

    if not source_path or not source_path.exists():
        print(f"  ⚠️  源不存在: {skill_name} ({source_path})")
        return False

    target_path = category_dir / skill_name

    try:
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.copytree(source_path, target_path)
        print(f"  ✓ 安装成功: {skill_name} (等级: {skill_info['level']})")
        return True
    except Exception as e:
        print(f"  ✗ 安装失败: {skill_name} - {e}")
        return False

def main():
    print("=" * 60)
    print("Skills 安装脚本")
    print("=" * 60)
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"安装目录: {SKILLS_DIR}")
    print()

    # 创建基础目录
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    total_installed = 0
    total_failed = 0

    for category_id, category_info in CATEGORIES.items():
        print(f"\n📁 {category_id}: {category_info['name']}")
        print("-" * 40)

        category_dir = SKILLS_DIR / category_id
        category_dir.mkdir(parents=True, exist_ok=True)

        for skill_name, skill_info in category_info["skills"].items():
            if install_skill(skill_name, skill_info, category_dir):
                total_installed += 1
            else:
                total_failed += 1

    print("\n" + "=" * 60)
    print(f"安装完成！成功: {total_installed}, 失败: {total_failed}")
    print("=" * 60)

    # 创建总 README
    create_main_readme()

def create_main_readme():
    """创建主 README 文件"""
    readme_content = """# Skills 安装清单

> 生成日期：2026-11-27

## 目录结构

```
.claude/skills/
├── 01-discovery-and-design/    # 需求发现与设计
├── 02-architecture-planning/   # 规格、架构与计划
├── 03-development/             # 开发与内容生成
├── 04-testing-security/        # 测试、质量与安全
├── 05-deployment/              # 发布与部署
├── 06-operations/              # 运维、维护与复盘
└── 07-integrations/            # AI 媒体与外部集成
```

## 推荐等级

| 等级 | 含义 |
|------|------|
| S | 核心 - 大多数团队应采用 |
| A | 推荐 - 对应场景收益明显 |
| B | 可选 - 特定技术栈使用 |

## 主链路推荐

```
office-hours → spec → plan-eng-review → design-review
→ review-agent → qa-only → cso → ship
→ land-and-deploy → canary → investigate → retro
```

## 使用方法

进入对应分类目录，查看各 skill 的 SKILL.md 文件。
"""

    readme_path = SKILLS_DIR / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"\n📝 已创建: {readme_path}")

if __name__ == "__main__":
    main()