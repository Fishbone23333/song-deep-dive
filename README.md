# 一歌一读 · song-deep-dive

**像每天读一篇文章那样，深入了解一首歌。**

歌曲可以是日常生活的背景，也可以成为一次值得慢下来的阅读。「一歌一读」是一个遵循 [Agent Skills](https://agentskills.io/specification) 规范的歌曲导读 Skill：从一条有依据的理解角度进入，结合歌曲信息、创作背景与按段落展开的歌词细读，带你读出作品的情绪和表达。读完再听，或许会多听见一层。默认支持中文和英语。

- 可以从明确的心情找歌请求、喜欢的歌手、指定歌曲、每日推荐或随机探索进入。
- 默认推荐先给 2—3 个候选；若你明确要一首歌，会在同一轮直接给出完整解读与约三个深入方向。
- 完整导读采用醒目的文章标题、已核实的歌曲信息表和按作品结构推进的细读：先读一小段连贯歌词，再看其中的用字与句间联系如何展开画面与情绪，最后连接全曲。
- 心情入口会把你的问题与作品具体连接；其他入口围绕作品本身展开。
- 记住明确喜欢的歌手，记录最近 90 天推荐过的歌以去重；不保存听歌历史、心情或个人经历。
- “我心情不好”本身不会触发找歌。定时、推送和播放由宿主处理。

## 安装

从 [GitHub 仓库](https://github.com/Fishbone23333/song-deep-dive) 安装（需要满足 [skills CLI](https://github.com/vercel-labs/skills) 的 Node.js 要求）：

```bash
npx skills add Fishbone23333/song-deep-dive --skill song-deep-dive -g
```

根据提示选择目标 Agent。也可以指定安装到 Codex 和 Claude Code：

```bash
npx skills add Fishbone23333/song-deep-dive --skill song-deep-dive -g -a codex -a claude-code
```

从本地克隆的项目安装时，将命令中的 `Fishbone23333/song-deep-dive` 替换为 `.`。

手动安装可按下方打包命令生成 `dist/song-deep-dive.zip`：解压出 `song-deep-dive` 文件夹，放到目标宿主文档指定的 Skill 目录。主流程没有固定的 Agent 工具名，也没有必须依赖的 OpenAI 元数据。

## 使用

使用目标宿主提供的技能调用方式，或直接提出明确的音乐请求：

> 我最近很迷茫，有哪些歌曲能给我指引？
>
> 我想了解 Taylor Swift 的 evermore 在讲什么。
>
> 给我今天的歌曲推荐。

第一次询问喜欢的歌手，可以跳过。选定歌曲后，会得到一篇有主张、有证据、有推进的导读：歌曲信息可用表格呈现，歌词按实际段落细读，中文释义与分析相邻，并以可靠背景串起全曲。读完后，还可以继续了解创作动机或相关时期经历，再带着新的理解回到音乐里。

## 记忆与权限

跨会话记忆保存在独立用户数据目录的 `preferences.json`：

| 系统 | 默认目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\song-deep-dive` |
| macOS | `~/Library/Application Support/song-deep-dive` |
| Linux | `$XDG_DATA_HOME/song-deep-dive`，未设置时为 `~/.local/share/song-deep-dive` |

可以配置绝对路径环境变量 `SONG_DEEP_DIVE_DATA_DIR`。多个本机 Agent 有权访问同一路径时，可以共用记忆；不提供跨设备同步。没有权限时，只在本会话记忆，不会自动在项目或 Skill 目录里另存一份。

推荐的文件辅助脚本使用 Python 3.10+ 标准库，无需 pip 安装依赖。没有 Python 时，宿主可以按照 [记忆约定](references/memory.md) 使用等价的可靠文件操作；无法持久化时仍可解读歌曲。使用本 Skill 不会因为安装本身而创建偏好文件。

## 能力要求与支持范围

| 能力 | 完整体验 | 不具备时 |
| --- | --- | --- |
| 支持 Agent Skills | 发现并加载核心指令 | 需要宿主增加标准支持或手动提供指令，无法保证自动发现。 |
| 网页搜索／读取 | 核实访谈、创作背景与引用 | 基于用户提供文本解读，说明背景未在线核实。 |
| 读写用户文件 | 保存歌手偏好与跨会话去重 | 仅在当前对话内记忆和去重。 |
| Python 3.10+ 或可靠等价文件操作 | 使用本地记忆辅助程序 | 仍可按上述限制完成当前歌曲请求。 |

安装器支持某个 Agent，只说明可将标准包安装到相应位置；实际工具、权限和对话表现仍需要在该宿主验证。

本地验证结果：

| 项目 | 状态 |
| --- | --- |
| Python 记忆与打包测试 | Windows／Python 3.14：22 项通过，覆盖并发去重、只读、损坏保护与 ZIP 内容。 |
| 标准格式与包发现 | Skill 格式校验通过，skills CLI 1.7.4 能识别。 |
| Codex、Claude Code 安装布局 | 在临时项目通过 skills CLI 安装；两份指令与源文件一致，不修改用户已安装技能。 |
| 两份安装副本共享数据 | 已验证：同一临时数据目录下读到相同歌手偏好，并排除已登记歌曲。 |
| 实际跨 Agent 对话体验 | 待按仓库内的 `tests/acceptance.md` 验证。 |
| macOS、Linux 实机文件权限与锁 | 待在对应系统验证；路径解析有模拟测试。 |

## 开发验证与打包

从项目根目录运行；Windows 可将 `python` 替换为 `py -3`：

```bash
python -B -m unittest discover -s tests -v
python -B scripts/build_release.py
```

输出 `dist/song-deep-dive.zip`，仅包含标准指令、必要参考、记忆脚本和使用说明；不包含个人数据、MVP 文档、测试和开发缓存。开发与测试均使用临时用户数据目录。

当前交付未替用户全局安装，也未初始化真实用户记忆。网络检索由运行 Skill 的宿主提供；本项目没有额外的音乐 API、账号或后台服务。

仓库中的 `歌曲背后故事-Skill-MVP方案.md` 记录产品需求，`tests/acceptance.md` 提供实际宿主验收场景；它们不随运行包分发。解读规范见 [资料与解读](references/listening-guide.md)。
