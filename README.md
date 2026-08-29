# Mini Coding Agent

一个从零实现的编程智能体（coding agent）：通过与大语言模型交互，自主读写文件、执行命令，完成编程任务。不依赖任何 agent 框架 / SDK，核心逻辑（对话管理、工具定义与本地执行、输出解析、循环终止、错误处理）全部自行实现。

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY
python main.py "任务描述" --workspace <目录>   # 单次任务
python main.py --workspace <目录>              # 交互式逐条输入
python main.py --plan "任务描述"                # 先生成计划，确认后执行
```

模型通过 OpenAI 兼容协议接入，默认 DeepSeek（`deepseek-chat`），改 `AGENT_BASE_URL` / `AGENT_MODEL` 可切换任意兼容网关。

## 工作原理

```
用户任务 → [循环] 调用模型 → 有 tool_calls？
              ↑                    ├─ 是 → 本地执行 → 结果回填 → 回到循环
              └── 否 → 输出最终回复，结束
```

**循环终止条件**（三层）：
1. 模型不再发起工具调用 → 任务完成；
2. 达到 `AGENT_MAX_TURNS` → 注入"停止使用工具"指令强制收尾；
3. 同一工具调用连续重复 3 次 → 插入警告打破死循环。

**工具**（OpenAI function calling 格式声明，全部本地执行）：
- `read_file` / `write_file` / `edit_file` / `list_files` / `run_command`
- `edit_file` 要求 `old_string` 唯一精确匹配，防止模型凭记忆盲改
- 所有路径限制在工作区内；工具输出有长度上限，防止撑爆上下文

**错误处理**：工具执行失败不中断循环，错误文本回传给模型由它自行修正；API 限流/网络/超时/5xx 指数退避重试，4xx 立即抛出；工具参数非法 JSON、未知工具、参数类型错误均以文本形式反馈给模型。

## 特色功能

- **上下文自动摘要**：CJK 按字、其余按 4 字符估算 token，超过阈值时把旧历史交给模型压缩成进度摘要，保留最近消息；切口自动避开 tool 消息保证配对合法，摘要失败兜底为直接丢弃。
- **Plan 模式**：`--plan` 时先由模型生成执行计划（规划阶段不携带工具），用户确认后计划注入任务上下文再执行。
- **危险命令确认**：`rm -r`、`git reset --hard`、`git push --force`、`sudo` 等黑名单命令执行前需用户确认；被拒绝时模型会自动改用更安全的替代方案。

## 测试

```bash
python -m pytest tests/ -v   # 18 例：上下文边界、压缩触发、卡死检测、收尾、错误回传、危险命令等
```

## 目录结构

```
main.py            # CLI 入口（任务模式 / REPL / --plan）
agent/config.py    # 配置：环境变量优先、.env 兜底
agent/llm.py       # OpenAI 兼容客户端封装（重试、摘要调用）
agent/loop.py      # 主循环：调用→解析→执行→回填，终止条件
agent/tools.py     # 工具 schema 声明与注册表
agent/executor.py  # 工具本地执行（含危险命令黑名单）
agent/context.py   # token 估算与自动摘要压缩
tests/             # pytest 测试套件
```
