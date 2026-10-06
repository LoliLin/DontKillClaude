# Claude 自动讨论器

用一份 JSON 配置，让本地或 GitHub Actions 定时调用 Claude Code CLI（`claude -p`），并把每次提示、回答和错误追加保存为 JSONL transcript。只依赖 Python 3 标准库。

## 快速开始

1. 安装并登录 [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview)，确保终端能运行 `claude`。
2. 复制 `config.example.json` 为 `config.json`，编辑其中的讨论内容和参数。
3. 运行：

   ```bash
   python claude_discuss.py --config config.json
   ```

   只运行一轮：

   ```bash
   python claude_discuss.py --config config.json --once
   ```

   配置文件默认名是 `config.json`。不要把 API key 或其他凭据写进配置或提交到仓库；Claude CLI 使用其自身的认证配置。程序不打印 prompt、回答或 CLI 原始错误到控制台，错误详情会做常见 token 格式脱敏后写进 transcript。Transcript 本身包含提示词和模型回答，请按敏感数据妥善保存。

## 配置

查看 `config.example.json`。主要字段：

- `sequences`：一个或多个消息序列，每条消息调用一次 `claude -p`。在对应 sequence 的 `messages` 数组中编辑主题和提示内容；可添加多个 sequence，每个 sequence 使用 `name` 和 `messages`，runner 会按配置顺序执行。
- `conversation_mode`：`independent` 每条消息都是独立调用（默认）；`chained` 在同一序列内用 Claude Code 的 `--session-id` 创建会话、后续用 `--resume` 续接。不同 sequence 和不同轮次使用不同会话。
- `rounds`：轮数，正整数；`0`、`"forever"` 或省略表示持续运行。
- `interval_seconds`：两轮开始之间等待的秒数。
- `timeout_seconds`：单次 CLI 调用超时秒数。
- `transcript_path`：JSONL 输出文件路径；父目录会自动创建。
- `claude_command`：Claude CLI 可执行文件名或路径。

`chained` 适合后续消息明确依赖前文的讨论；如果每条提示都应从空白上下文开始，使用 `independent`。连续调用会各自产生一条 transcript 记录，非零退出码或超时会记录错误并停止当前进程，避免故障时无限重试。

## GitHub Actions 定时运行

`.github/workflows/claude-discuss.yml` 每日使用仓库根目录的 `config.json`。仓库中的该文件是可编辑的讨论配置，确保定时任务的默认路径存在。编辑并提交 `config.json` 即可调整自动讨论主题和消息；`config.example.json` 是复制参考模板。Actions 每次执行使用 `rounds: 1`，由 cron 负责重复调度。

手动运行时，在 **Actions → Claude discussion → Run workflow** 的 `config_path` 输入中选择仓库里的 JSON 配置路径，默认是 `config.json`。路径相对于仓库根目录。

GitHub Actions 使用 Claude Code OAuth 订阅令牌认证：

1. 在已登录 Claude Code 的本地机器上运行 `claude setup-token`，按提示生成 OAuth token。请勿在共享机器上执行，也不要把命令输出贴到聊天、日志或其他共享位置。
2. 在 GitHub 仓库打开 **Settings → Secrets and variables → Actions → Secrets**，创建 repository secret `CLAUDE_CODE_OAUTH_TOKEN`，值粘贴 `claude setup-token` 输出的 token。
3. 工作流会将该 secret 作为同名环境变量传给 Claude CLI。token 绑定到生成它的 Claude 账号及其订阅权限，请像密码一样保管；轮换时重新生成并更新 GitHub secret。

若提示内容不应提交到 Git，推荐在 private 仓库中维护 `config.json`。另一种方式是在 Actions secrets 中设置 `DISCUSSION_CONFIG_JSON`，值为完整 JSON 配置；设置后它会覆盖该次运行所选路径的文件内容，并用于定时和手动运行。可复制 `config.example.json` 内容后编辑 `sequences` 中的主题和消息，再将完整 JSON 保存为 secret。不要将凭据写进讨论配置或 artifact。Transcript 会包含提示词和模型回答，应按敏感数据妥善保存。

如需保留 transcript，可按需上传 `transcripts/` 作为 artifact；该目录已从 Git 跟踪中排除。也可选择 Anthropic API key 认证，但这需要单独配置 API 计费和权限。

## Transcript 格式

每行一个 JSON 对象，包含 UTC 时间、轮次、序列名、turn 序号、模式、会话 ID、提示、退出码、回答和脱敏后的错误文本。工作流可按需求上传 `transcripts/` 作为 artifact。运行生成的 transcript 不应提交到 Git。
