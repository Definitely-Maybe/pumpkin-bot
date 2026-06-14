"""角色池管理 — self.md 提取 + LLM 虚构角色生成。"""

import json
import uuid
from typing import Optional
import aiosqlite

from ..storage.models import SocialCharacter
from ..storage import queries as q


class CharacterManager:
    """角色池管理。"""

    # 从 self.md 提取的真实人物（硬编码基础信息，故事不靠他们）
    _SELF_MD_CHARACTERS: list[dict] = [
        {
            "character_id": "wtt",
            "name": "wtt",
            "traits": ["傲娇", "学霸", "嘴硬心软", "口是心非"],
            "core_tension": "嘴上说'滚'但其实在等南瓜的消息",
            "relationship_to_nan_gua": "暧昧未确认——互怼但互相在意",
            "allowed_arc_types": ["romance", "conflict"],
        },
        {
            "character_id": "ccx",
            "name": "ccx",
            "traits": ["独立", "理性", "有男友但偶尔困惑"],
            "core_tension": "对南瓜有过感觉但选择了别人——现在维持微妙友谊",
            "relationship_to_nan_gua": "前暧昧对象，现在是保持距离的朋友",
            "allowed_arc_types": ["conflict", "growth"],
        },
        {
            "character_id": "mxt",
            "name": "mxt",
            "traits": ["敏感", "情绪化", "容易依赖人"],
            "core_tension": "需要南瓜的注意力但南瓜给不了稳定的回应",
            "relationship_to_nan_gua": "暧昧对象，关系不稳定",
            "allowed_arc_types": ["romance", "daily"],
        },
        {
            "character_id": "mcyy",
            "name": "mcyy",
            "traits": ["直球", "搞笑", "讲义气", "偶尔过于直白得罪人"],
            "core_tension": "把一切都变成玩笑——包括自己真正的困扰",
            "relationship_to_nan_gua": "好兄弟，互损但不记仇",
            "allowed_arc_types": ["daily", "conflict"],
        },
        {
            "character_id": "yanjielin",
            "name": "yanjielin",
            "traits": ["温柔", "有经验", "喜欢给人建议"],
            "core_tension": "看似什么都懂但自己的事处理得一团乱",
            "relationship_to_nan_gua": "前辈/指导者，南瓜会向她求助",
            "allowed_arc_types": ["growth", "daily"],
        },
        {
            "character_id": "taixiaodan",
            "name": "taixiaodan",
            "traits": ["严格", "关心学生", "偶尔露温柔"],
            "core_tension": "嘴上严格但私底下为学生操碎了心",
            "relationship_to_nan_gua": "敬畏的老师，南瓜在她面前会收敛",
            "allowed_arc_types": ["growth"],
        },
    ]

    def __init__(self, db: aiosqlite.Connection, llm=None):
        self.db = db
        self.llm = llm

    # ─── public API ──────────────────────────────────────────

    async def get_or_init_characters(self) -> list[SocialCharacter]:
        """获取角色池——首次无角色时初始化。"""
        existing = await q.get_all_characters(self.db)
        if not existing:
            await self._init_characters()
            existing = await q.get_all_characters(self.db)
        return [self._dict_to_char(d) for d in existing]

    async def get_fictional_count(self) -> int:
        chars = await q.get_all_characters(self.db)
        return sum(1 for c in chars if c["source"] == "fictional")

    # ─── init ────────────────────────────────────────────────

    async def _init_characters(self):
        """首次初始化：写入 self.md 角色 + LLM 生成虚构角色。"""
        for cdata in self._SELF_MD_CHARACTERS:
            char = self._dict_to_char(cdata)
            char.source = "self_md"
            await q.upsert_character(self.db, char)

        if self.llm:
            fictional = await self._generate_fictional(4)
            for cdata in fictional:
                await q.upsert_character(self.db, cdata)

    async def _generate_fictional(self, count: int) -> list[SocialCharacter]:
        """LLM 生成虚构角色池（含 core_tension）。"""
        prompt = self._build_fictional_prompt("华东师大、合肥、杭州")
        try:
            response = await self.llm.client.chat.completions.create(
                model=self.llm.model,
                max_tokens=1024,
                temperature=0.9,
                messages=[
                    {"role": "system", "content": (
                        "你是小说的角色设计师。创造有深度、有矛盾的角色。"
                        "不要脸谱化——每个人都要有内在冲突。"
                    )},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            chars = []
            for item in data.get("characters", [])[:count]:
                cid = f"fictional_{uuid.uuid4().hex[:8]}"
                chars.append(SocialCharacter(
                    character_id=cid,
                    name=item["name"],
                    source="fictional",
                    traits=json.dumps(item.get("traits", []), ensure_ascii=False),
                    core_tension=item.get("core_tension", ""),
                    relationship_to_nan_gua=item.get("relationship_to_nan_gua", ""),
                    allowed_arc_types=json.dumps(item.get("allowed_arc_types", []), ensure_ascii=False),
                ))
            return chars
        except (json.JSONDecodeError, Exception):
            return []

    # ─── helpers ─────────────────────────────────────────────

    @classmethod
    def _load_self_md_characters(cls) -> list[SocialCharacter]:
        return [cls._dict_to_char(c) for c in cls._SELF_MD_CHARACTERS]

    @classmethod
    def _dict_to_char(cls, d: dict) -> SocialCharacter:
        return SocialCharacter(
            character_id=d["character_id"],
            name=d.get("name", d["character_id"]),
            source=d.get("source", "fictional"),
            traits=d.get("traits", "[]") if isinstance(d.get("traits"), str)
                   else json.dumps(d.get("traits", []), ensure_ascii=False),
            core_tension=d.get("core_tension", ""),
            relationship_to_nan_gua=d.get("relationship_to_nan_gua", ""),
            current_arc_id=d.get("current_arc_id"),
            arc_cooldown_until=d.get("arc_cooldown_until"),
            status=d.get("status", "active"),
            allowed_arc_types=d.get("allowed_arc_types", "[]") if isinstance(d.get("allowed_arc_types"), str)
                             else json.dumps(d.get("allowed_arc_types", []), ensure_ascii=False),
        )

    @classmethod
    def _build_fictional_prompt(cls, env_hint: str) -> str:
        return (
            f"南瓜是一个大学生，在{env_hint}。请为他创造 4 个虚构的同学/室友/社团朋友角色。\n\n"
            "要求：\n"
            "1. 每个角色都要有 **core_tension**（核心矛盾）——这是推动故事的冲突点，"
            "不要让角色变成标签堆砌。例：不是'二次元室友'而是'社恐二次元，但聊到专业领域时敢跟教授吵架'\n"
            "2. 至少一个角色有暧昧线潜质（可以发展 rommance 弧）\n"
            "3. 至少一个角色是'天天互怼的损友'（适合 daily/conflict 弧）\n"
            "4. 角色之间应该有关系（室友/同学/暗恋等）\n"
            "5. 每个角色标注 allowed_arc_types（可选的弧类型：romance, conflict, growth, daily）\n\n"
            '返回 JSON：{"characters": [{"name": "...", "traits": [...], '
            '"core_tension": "...", "relationship_to_nan_gua": "...", '
            '"allowed_arc_types": [...]}, ...]}'
        )
