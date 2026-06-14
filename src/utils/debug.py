"""DebugLogger — 开发者调试输出，写到 stderr。"""

import sys
from datetime import datetime


class DebugLogger:
    """叙事 + 数据嵌入式调试日志。"""

    def __init__(self, level: int = 0, target=None):
        self.level = level
        self._out = target or sys.stderr
        self._turn = 0

    def _emit(self, text: str):
        if self.level > 0:
            print(text, file=self._out, flush=True)

    def _emit_stage(self, text: str):
        if self.level >= 2:
            print(text, file=self._out, flush=True)

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ─── level 2: pipeline 阶段 ──────────────────────────

    def turn_start(self, user_id: str, platform: str,
                   message: str, timestamp: str = ""):
        self._turn += 1
        ts = timestamp or self._ts()
        text = (
            f"\n═══ 第 {self._turn} 轮 · {user_id} · {platform} · {ts} ═══\n\n"
            f'\U0001F4E5 收到："{message}"'
        )
        self._emit_stage(text)

    def session(self, familiarity: float, rel_type: str,
                interaction_count: int, streak: int, branch_type: str = ""):
        branch_info = ""
        if branch_type:
            branch_info = (
                f"\n   趋势 {streak:+d}"
                f"（{branch_type} 方向，连续 {abs(streak)}/5）"
            )
        elif streak != 0:
            branch_info = f"\n   趋势 {streak:+d}（无明确方向）"
        text = (
            f"\n👤 南瓜认识他。\n"
            f"   关系：{rel_type} · 熟悉度 {familiarity:.2f} · 互动 {interaction_count} 轮"
            f"{branch_info}"
        )
        self._emit_stage(text)

    def context(self, token_est: int, cold_hits: int,
                warmth: float = 0, disclosure: float = 0,
                l4_str: str = ""):
        text = (
            f"\n🧠 上下文，约 {token_est} tokens\n"
            f"   冷记忆命中 {cold_hits} 条"
        )
        if l4_str:
            text += f"\n   {l4_str}"
        elif warmth > 0:
            text += f"\n   L4: warmth={warmth:.2f} disclosure={disclosure:.2f}"
        self._emit_stage(text)

    def llm(self, model: str, elapsed: float,
            in_tokens: int, out_tokens: int):
        text = (
            f"\n🤖 {model} · {elapsed:.1f}s · "
            f"{in_tokens}→{out_tokens} tokens"
        )
        self._emit_stage(text)

    def reply(self, text_preview: str, max_len: int = 80):
        preview = text_preview[:max_len] + ("..." if len(text_preview) > max_len else "")
        self._emit_stage(f'\n📤 "{preview}"')

    def turn_end(self, total_elapsed: float):
        self._emit_stage(f"\n── 总耗时 {total_elapsed:.1f}s ───")

    # ─── level 1+: sidecar 步骤 ──────────────────────────

    def sidecar(self, index: int, icon: str, name: str, detail: str = ""):
        lines = [f" #{index:<2} {icon} {name}"]
        if detail:
            for dline in detail.split("\n"):
                lines.append(f"      {dline}")
        self._emit("\n".join(lines))

    def sidecar_header(self):
        self._emit("\n── 后台处理 ───────────────────────────────")
