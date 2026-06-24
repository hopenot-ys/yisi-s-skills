# Trae Skills

个人积累的 Trae IDE skill 集合。每个 skill 是一个自包含的子目录，可独立使用。

## 包含的 Skills

| Skill | 说明 | 入口 |
|---|---|---|
| summary-quality-checker | 证券研报 summary 质量审核工具，检查合规性、忠实性、投资建议、交易诱导、收益承诺、风险弱化、不可溯源等问题 | [进入 →](.agents/skills/summary-quality-checker/) |

## 目录结构

```
skill_test/
├── .gitignore
├── README.md                       ← 本文件
├── true_demo_input.csv            ← 测试输入示例
├── true_demo_output_generated.csv ← 测试输出示例
└── .agents/
    └── skills/
        └── summary-quality-checker/   ← 单个 skill 自包含目录
            ├── SKILL.md
            ├── README.md
            ├── config.example.yaml
            ├── references/
            ├── scripts/
            └── examples/
```

## 使用方式

1. 进入对应 skill 目录，参考其各自的 `README.md` 了解运行方式。
2. 一般流程：在 skill 目录下执行 `python scripts/check_csv.py --input <输入.csv> --output <输出.csv>`。
3. 详细参数与示例见各 skill 的 `SKILL.md` 和 `README.md`。

## 新增 Skill

在 `.agents/skills/` 下新建一个以 skill 名称命名的子目录，保持自包含结构（不依赖其他 skill），并在本文件表格中追加一行说明。

## 说明

- 本仓库为初筛工具集合，不替代正式合规审核。
- 真实 API key 等敏感信息通过环境变量传入，不要写入版本库（`.gitignore` 已忽略 `config.yaml`）。
