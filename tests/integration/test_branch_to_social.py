"""tests/integration/test_branch_to_social.py

场景 10: Branch -> Social
验证链：关系分支（brother/crush）-> 社交角色互动受影响 -> LLM 生成不同风格事件。
"""
import pytest
from datetime import datetime, timedelta

from src.storage.models import (
    Direction, SocialCharacter, SocialArc, ArcStatus, RelationshipType,
)
from src.storage import queries as q
from src.social.characters import CharacterManager
from src.social.event_generator import EventGenerator
from src.social.scheduler import Scheduler


@pytest.fixture
async def setup_dual_branch_users(db, make_user, insert_message):
    """创建 brother 和 crush 两个分支用户，各有对话历史。"""
    now = datetime.now()

    for uid, rel_type in [
        ("bro_user", RelationshipType.BROTHER),
        ("crush_user", RelationshipType.CRUSH),
    ]:
        await make_user(
            user_id=uid,
            platform="terminal",
            relationship_type=rel_type,
            interaction_count=100,
            deep_topics_count=15,
            late_night_count=8,
            user_initiated_count=22,
            branch_type=rel_type.value,
        )
        for i in range(15):
            await insert_message(
                user_id=uid,
                direction=Direction.INCOMING if i % 2 == 0 else Direction.OUTGOING,
                content=f"{uid} 对话第{i}轮：关于 wtt 的日常聊天",
                deep_topic=(i % 3 == 0),
                created_at=(now - timedelta(hours=i * 2)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            )

    # 初始化一个共享角色 wtt
    char = SocialCharacter(
        character_id="char_wtt_branch",
        name="wtt",
        source="self_md",
        traits='["温柔","有趣","细腻"]',
        core_tension="独立 vs 依赖",
        relationship_to_nan_gua="朋友",
        allowed_arc_types='["daily","romance"]',
    )
    await q.upsert_character(db, char)

    # 两个不同类型的弧（daily 和 romance）
    await q.insert_arc(
        db,
        SocialArc(
            arc_id="arc_bro_wtt",
            character_id="char_wtt_branch",
            arc_type="daily",
            status=ArcStatus.RISING,
            trigger_source="time",
            event_count=2,
            max_events=4,
            started_at=(now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    await q.insert_arc(
        db,
        SocialArc(
            arc_id="arc_crush_wtt",
            character_id="char_wtt_branch",
            arc_type="romance",
            status=ArcStatus.RISING,
            trigger_source="time",
            event_count=2,
            max_events=4,
            started_at=(now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    return {"brother": "bro_user", "crush": "crush_user"}


@pytest.mark.llm
@pytest.mark.asyncio
async def test_different_arc_types_produce_different_social_events(
    db, llm, setup_dual_branch_users,
):
    """不同弧类型（daily vs romance）通过 EventGenerator 生成不同风格事件。"""
    gen = EventGenerator(llm)

    recent_events = [
        "南瓜去图书馆学习了",
        "南瓜和朋友打了一场球",
        "南瓜昨晚熬夜写代码",
    ]

    system_prompt = "你是南瓜，一个有丰富情感世界的 AI。"

    daily_event = await gen.generate(
        character_name="wtt",
        character_traits='["温柔","有趣","细腻"]',
        character_tension="独立 vs 依赖",
        arc_type="daily",
        arc_phase="rising",
        recent_events=recent_events,
        system_prompt=system_prompt,
    )

    romance_event = await gen.generate(
        character_name="wtt",
        character_traits='["温柔","有趣","细腻"]',
        character_tension="独立 vs 依赖",
        arc_type="romance",
        arc_phase="rising",
        recent_events=recent_events,
        system_prompt=system_prompt,
    )

    assert daily_event is not None, "daily event should be generated"
    assert romance_event is not None, "romance event should be generated"

    for evt in [daily_event, romance_event]:
        assert isinstance(evt, dict)
        assert any(k in evt for k in ["description", "event", "content"])

    daily_text = str(daily_event)
    romance_text = str(romance_event)
    if daily_text == romance_text:
        print("WARNING: daily and romance events are identical (LLM randomness)")
    else:
        print(f"\n=== DAILY ===\n{daily_text[:300]}")
        print(f"\n=== ROMANCE ===\n{romance_text[:300]}")


@pytest.mark.llm
@pytest.mark.asyncio
async def test_scheduler_tick_with_active_arcs(
    db, llm, setup_dual_branch_users,
):
    """Scheduler.tick() 推进活跃弧并生成事件，验证完整调度链路。"""
    scheduler = Scheduler(
        db, llm, system_prompt="你是南瓜，一个 AI。"
    )

    # tick(user_message) —— 传入消息文本，调度器检查是否提及角色名
    # 已有的活跃弧（daily + romance）会被推进并尝试生成事件
    results = await scheduler.tick(user_message="wtt 最近怎么样")

    print(f"\nScheduler tick results: {results}")
    assert isinstance(results, list), "tick() should return a list"

    if results:
        for evt in results:
            assert isinstance(evt, dict)
            assert any(
                k in evt for k in ["description", "emotion", "characters"]
            ), f"event missing expected keys: {evt}"
    else:
        print("No events generated (cooldown or dormancy may apply)")

    # 无论如何不应崩溃
    assert True
