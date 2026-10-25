# 偏好与推荐去重

首次使用、偏好维护和准备推荐时使用。记忆只包含首次流程状态、明确喜欢的歌手、最近 90 天推荐展示记录。以下为本 Skill 的约定，不是宿主统一提供的记忆 API。

## 路径与权限

1. 先用绝对路径环境变量 `SONG_DEEP_DIVE_DATA_DIR`，若设置了它，文件为其中的 `preferences.json`。
2. 否则按当前操作系统解析：Windows 使用 `%LOCALAPPDATA%\song-deep-dive`（缺省为用户主目录的 `AppData\Local\song-deep-dive`）；macOS 使用 `~/Library/Application Support/song-deep-dive`；Linux 使用 `$XDG_DATA_HOME/song-deep-dive`，未设置则使用 `~/.local/share/song-deep-dive`。

多个本机 Agent 使用相同路径且均有权限时可复用。远程主机、容器、不同设备不会自动同步。数据不得放入 Skill 安装文件夹；不要改写宿主的系统环境变量，也不要为“解决权限”自行在项目里建立第二份记忆。

读与写权限分别判断。缺失文件允许在首次明确回答或跳过时初始化；读取被拒绝、JSON 损坏、版本未知都不能当作新用户覆盖。修改仅在用户要求、明确表达偏好或当前推荐需要登记时进行；不从网页、歌词或单次艺人查询推断长期偏好。

## 首选辅助脚本

若宿主可执行 Python 3.10+，优先使用 Skill 根目录下的 `scripts/memory.py`，它仅依赖标准库。找到宿主实际可用的 Python 命令；下例的 `python` 可替换成 `python3` 或 Windows `py -3`。命令中的相对路径以 Skill 根目录为基准；从其他目录运行时将脚本路径作为一个完整的参数传入。

日期使用用户／宿主提供的当地日期，每次通过 `--today YYYY-MM-DD` 明确传入，避免执行机时区改变去重边界。例子日期仅作演示。

```bash
python scripts/memory.py --today 2026-10-25 show
python scripts/memory.py --today 2026-10-25 onboard --artist "Taylor Swift" --artist "Ariana Grande"
python scripts/memory.py --today 2026-10-25 onboard --skip
python scripts/memory.py --today 2026-10-25 artists add --artist "陈奕迅"
python scripts/memory.py --today 2026-10-25 artists remove --artist "Taylor Swift"
python scripts/memory.py --today 2026-10-25 artists set --artist "Ariana Grande"
python scripts/memory.py --today 2026-10-25 filter --track "evermore" "Taylor Swift" --track "ghostin" "Ariana Grande"
python scripts/memory.py --today 2026-10-25 record --if-new --track "evermore" "Taylor Swift" --track "ghostin" "Ariana Grande"
python scripts/memory.py --today 2026-10-25 clear --scope recommendations
python scripts/memory.py --today 2026-10-25 clear --scope artists
python scripts/memory.py --today 2026-10-25 clear --scope all
```

向命令传入歌手或曲名时使用正确的参数传递与引用，不把用户文本拼成可执行命令；可用结构化参数时优先使用。不会处理参数边界的宿主可只读文件、在对话内临时记忆，或用其允许的等价文件操作。

脚本行为：

- `show` 和 `filter` 只读；文件缺失时返回空状态，不创建文件或目录，不代表已经有写权限。
- `onboard` 保存明确给出的歌手或跳过状态。`artists` 维护偏好，`clear artists` 保留已完成的首次状态。
- `filter` 将候选分为 `available` 和 `excluded`。按曲名与主艺人做 Unicode、空白和大小写归一；译名、别名、现场版需由 Agent 先确认身份，不能自动视为不同歌曲躲过去重。
- `record --if-new` 一次登记 2—3 首已决定要展示的候选，日期为传入的当地日期。锁内再次检查近期记录，返回 `recorded` 与 `already_recent`，防止另一个 Agent 刚登记了相同歌曲。只展示本次成功登记的候选；冲突时最多补选两轮。省略 `--if-new` 会刷新相同曲目日期，一般推荐使用前者。写入时清理 90 天前的旧记录，不登记用户主动指定或选择重访的歌曲。
- 命令返回 JSON；`ok: true` 且 `saved: true` 才表示写入成功。失败以非零退出码和 `error.code` 返回，不应继续声称已经持久化。
- 修改采用操作系统文件锁并在锁内重新读取，再原子替换。锁随进程退出释放，保留的 `.lock` 文件不是活跃锁的证明，不要手动删它来抢写。

`clear --scope all` 清空本 Skill 的数据并恢复首次流程状态。仅在用户明确要求清空时使用，不为了修复读取错误擅自清空。

## 宿主只能做文件读写时

可以执行同样的模式，但必须保留读取失败和文件缺失的区别、校验版本、只修改对应字段、保留已有记录，并尽量使用宿主的原子更新与并发控制。如果无法可靠完成写入，只读已有偏好并用当前会话记录新增推荐，说明本次变化没有长期保存。不要用无保护的整文件覆盖假装具备并发持久化。

格式示意（歌名与歌手组成的标识为脚本生成的规范字符串）：

```json
{
  "schema_version": 1,
  "onboarding_status": "completed",
  "favorite_artists": ["Taylor Swift"],
  "recent_recommendations": [
    {"track_id": "[\"taylor swift\",\"evermore\"]", "recommended_on": "2026-10-25"}
  ]
}
```

保留当前日期及前 89 天的记录，未来日期也保留以避免错误时钟造成记录丢失。数据文件严格校验，不接受额外个人信息字段；不认识的版本或损坏文件保持原状。

## 面向听众的说明

只在限制影响当前体验时简短说明，例如“这次我能参考你的偏好，但新增记录暂时保存不了，跨会话去重可能不完整。”不要在正常找歌流程展示 JSON、锁或技术诊断。保存失败不阻止解读；无网络也不影响本来可用的记忆。
