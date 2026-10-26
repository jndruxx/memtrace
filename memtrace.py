"""memtrace —— 把智能体的记忆写入过程记成可查的轨迹。

设计原则：
1. **每条记忆都要有来路**。来源、保留理由、被谁覆盖，都得记下来。
2. **记录，不干预**。这个工具只做轨迹的存取与核对，绝不替智能体决定记什么。
3. **覆盖必须显式**。记忆被替换时，前后两条都留着。

仅依赖 Python 标准库。

用法:
    python memtrace.py --help
    python memtrace.py --trace mem.jsonl --show
    python memtrace.py --trace mem.jsonl --stats --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# 事件模型
# ---------------------------------------------------------------------------

EVENT_KINDS = ("write", "hit", "miss", "update", "evict", "decay")

# 记忆保留的理由类别
REASONS = ("explicit_user", "task_result", "preference", "fact", "summary", "other")


def new_event(kind: str, key: str, **extra) -> dict:
    """构造一条轨迹事件。"""
    if kind not in EVENT_KINDS:
        raise ValueError(f"未知事件类型：{kind}（可用：{', '.join(EVENT_KINDS)}）")
    ev = {"kind": kind, "key": key, "ts": time.time()}
    ev.update({k: v for k, v in extra.items() if v is not None})
    return ev


# ---------------------------------------------------------------------------
# 轨迹存取
# ---------------------------------------------------------------------------

def load_trace(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError as e:
        raise ValueError(f"读不了 {path}：{e}") from e

    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e
        return [x for x in data if isinstance(x, dict)]

    events: list[dict] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {lineno} 行 JSON 解析失败：{e}") from e
        if isinstance(obj, dict):
            events.append(obj)
    return events


def append_event(path: str, event: dict) -> None:
    """追加一条事件。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 记忆账本
# ---------------------------------------------------------------------------

def build_ledger(events: list[dict]) -> dict:
    """从轨迹重建记忆账本：每条记忆的来源、命中、覆盖。"""
    ledger: dict[str, dict] = {}

    for ev in events:
        kind = ev.get("kind")
        key = ev.get("key", "")
        if not key:
            continue

        entry = ledger.setdefault(key, {
            "key": key,
            "writes": 0,
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "reason": "",
            "source": "",
            "content": "",
            "first_ts": ev.get("ts"),
            "last_ts": ev.get("ts"),
            "status": "unknown",
            "history": [],
        })

        entry["last_ts"] = ev.get("ts", entry["last_ts"])
        entry["history"].append({
            "kind": kind, "ts": ev.get("ts"),
            "replaced": ev.get("replaced"),
            "note": ev.get("note", ""),
        })

        if kind == "write":
            entry["writes"] += 1
            entry["status"] = "active"
            if ev.get("reason"):
                entry["reason"] = ev["reason"]
            if ev.get("source"):
                entry["source"] = ev["source"]
            if ev.get("content"):
                entry["content"] = ev["content"]
        elif kind == "hit":
            entry["hits"] += 1
        elif kind == "miss":
            entry["misses"] += 1
        elif kind == "update":
            entry["writes"] += 1
            entry["status"] = "active"
            if ev.get("reason"):
                entry["reason"] = ev["reason"]
            if ev.get("content"):
                entry["content"] = ev["content"]
        elif kind == "evict":
            entry["evictions"] += 1
            entry["status"] = "evicted"
        elif kind == "decay":
            entry["status"] = "decayed"

    for entry in ledger.values():
        if entry["writes"] > 0 and entry["status"] == "unknown":
            entry["status"] = "active"

    return ledger


def analyze(events: list[dict]) -> dict:
    """整条轨迹的分析。"""
    ledger = build_ledger(events)

    by_reason = Counter()
    for e in ledger.values():
        if e["reason"]:
            by_reason[e["reason"]] += 1

    by_status = Counter(e["status"] for e in ledger.values())

    kind_counts = Counter(ev.get("kind", "") for ev in events)

    # 被覆盖的记忆：同一个 key 被写了多次
    overwritten = {k: v for k, v in ledger.items() if v["writes"] > 1}

    # 没有来源的记忆：来路不明的
    no_source = {k: v for k, v in ledger.items()
                 if v["writes"] > 0 and not v["source"]}

    # 命中率
    total_lookups = kind_counts.get("hit", 0) + kind_counts.get("miss", 0)
    hit_rate = (kind_counts.get("hit", 0) / total_lookups) if total_lookups else None

    # 写入来源分布
    write_sources = Counter(
        ev.get("source", "未标注") for ev in events if ev.get("kind") == "write")

    return {
        "event_count": len(events),
        "memory_count": len(ledger),
        "kind_counts": dict(kind_counts),
        "by_status": dict(by_status),
        "by_reason": dict(by_reason),
        "write_sources": dict(write_sources),
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "overwritten": {k: {"writes": v["writes"], "source": v["source"]}
                        for k, v in overwritten.items()},
        "no_source": sorted(no_source),
        "ledger": ledger,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render(result: dict) -> str:
    out: list[str] = []
    out.append("记忆轨迹分析")
    out.append("=" * 60)
    out.append(f"事件 {result['event_count']} 条 ｜ 记忆 {result['memory_count']} 条")
    if result["hit_rate"] is not None:
        out.append(f"命中率 {result['hit_rate']:.1%}")
    out.append("")

    out.append("事件分布：" + "、".join(
        f"{k} {v}" for k, v in sorted(result["kind_counts"].items())))
    out.append("记忆状态：" + "、".join(
        f"{k} {v}" for k, v in sorted(result["by_status"].items())))
    if result["by_reason"]:
        out.append("保留理由：" + "、".join(
            f"{k} {v}" for k, v in sorted(result["by_reason"].items())))
    if result["write_sources"]:
        out.append("写入来源：" + "、".join(
            f"{k} {v}" for k, v in sorted(result["write_sources"].items())))
    out.append("")

    if result["overwritten"]:
        out.append("被覆盖过的记忆（前后版本都留在轨迹里）：")
        for k, v in result["overwritten"].items():
            out.append(f"  · {k}  写了 {v['writes']} 次  来源 {v['source'] or '未标注'}")
        out.append("")

    if result["no_source"]:
        out.append("没有来源标注的记忆（来路不明）：")
        for k in result["no_source"]:
            out.append(f"  · {k}")
        out.append("")

    out.append("记忆清单：")
    for k, e in sorted(result["ledger"].items()):
        out.append(f"  {k}")
        out.append(f"    状态 {e['status']} ｜ 写 {e['writes']} 次 ｜ "
                   f"命中 {e['hits']} 次 ｜ 淘汰 {e['evictions']} 次")
        out.append(f"    来源 {e['source'] or '未标注'} ｜ "
                   f"理由 {e['reason'] or '未标注'}")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="memtrace",
        description="把智能体的记忆写入过程记成可查的轨迹（仅依赖标准库）",
        epilog=(
            "事件格式：\n"
            "  {\"kind\":\"write\",\"key\":\"user.likes.dark_mode\","
            "\"source\":\"chat#12\",\"reason\":\"explicit_user\","
            "\"content\":\"偏好暗色模式\"}\n"
            "  python memtrace.py --trace mem.jsonl --stats\n"
            "  python memtrace.py --trace mem.jsonl --append --kind write "
            "--key k --source chat#1 --reason preference\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--trace", required=True, help="轨迹文件（JSONL）")
    ap.add_argument("--stats", action="store_true", help="输出统计与账本")
    ap.add_argument("--append", action="store_true", help="追加一条事件")
    ap.add_argument("--kind", help="事件类型：" + "、".join(EVENT_KINDS))
    ap.add_argument("--key", help="记忆键")
    ap.add_argument("--source", help="来源（会话 / 消息 id）")
    ap.add_argument("--reason", help="保留理由：" + "、".join(REASONS))
    ap.add_argument("--content", help="记忆内容")
    ap.add_argument("--replaced", help="覆盖时记下被替换的键")
    ap.add_argument("--note", help="备注")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.append:
        if not args.kind or not args.key:
            print("--append 需要 --kind 与 --key。", file=sys.stderr)
            return 2
        try:
            ev = new_event(args.kind, args.key, source=args.source,
                           reason=args.reason, content=args.content,
                           replaced=args.replaced, note=args.note)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        try:
            append_event(args.trace, ev)
        except OSError as e:
            print(f"写不了轨迹文件：{e}", file=sys.stderr)
            return 2
        print(f"已记录：{args.kind} {args.key}")
        return 0

    try:
        events = load_trace(args.trace)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not events:
        print("轨迹是空的。", file=sys.stderr)
        return 2

    result = analyze(events)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.stats:
        print(render(result))
        return 0

    # 默认：逐条列出轨迹
    for ev in events:
        parts = [f"{ev.get('ts', 0):>14.3f}", f"{ev.get('kind', ''):<8}",
                 ev.get("key", "")]
        if ev.get("source"):
            parts.append(f"  来源 {ev['source']}")
        if ev.get("reason"):
            parts.append(f"  理由 {ev['reason']}")
        if ev.get("replaced"):
            parts.append(f"  覆盖 {ev['replaced']}")
        if ev.get("note"):
            parts.append(f"  {ev['note']}")
        print(" ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
