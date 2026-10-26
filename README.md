# memtrace

**把智能体的记忆写入过程记成可查的轨迹。**

`memtrace` —— 记录记忆的写入、命中与覆盖过程，说明每条记忆为何被保留。

- 零依赖，Python 3.10+ 标准库即可运行
- 单文件，`memtrace.py` 拷走就能用
- 不联网、不写文件

<!-- ipos:install -->
## 安装

零依赖，Python 3.10+ 即可：

```bash
pip install jndruxx-memtrace
```

装完直接用命令名调用：

```bash
memtrace --help
```

也可以不用安装，直接把 `memtrace.py` 拷走用——它只依赖标准库。

## 为什么需要它

记忆工具多只提供存取接口；memtrace 记录每条记忆的来源与去留理由，让记忆账本可核对。

它遵守下面几条自己定的规矩：

1. **每条记忆都要有来路**。来源、保留理由、被谁覆盖，都得记下来。
2. **记录，不干预**。这个工具只做轨迹的存取与核对，绝不替智能体决定记什么。
3. **覆盖必须显式**。记忆被替换时，前后两条都留着。

## 用法

```bash
python memtrace.py --trace mem.jsonl --show
python memtrace.py --trace mem.jsonl --stats --json
```

加 `--json` 可以拿到机器可读的结果，便于接到流水线里。

## 已知局限

- 记忆账本只记录调用方写进来的内容，不做语义去重。
- 遗忘策略按时间与访问次数近似，不判断「这条记忆还有没有用」。
- 不加密存储，敏感内容请自行处理。

## 跑测试

```bash
python test_memtrace.py
```

测试用独立的断言与临时数据，不污染工作目录。

## 来源与参考

- Python 标准库文档：<https://docs.python.org/3/>
- GitHub 仓库：<https://github.com/jndruxx/memtrace>

---

## 关于作者

jndruxx 做智能体记忆的可追溯性相关的问题。这个工具先替你回答一个具体问题，再谈别的。

- 个人主页：<https://jndruxx.github.io>
- 仓库：<https://github.com/jndruxx/memtrace>

## 许可

MIT，见 [LICENSE](LICENSE)。
