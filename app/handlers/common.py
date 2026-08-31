from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..db import loads
from ..game_data import GOODS
from ..keyboards import (
    bag_keyboard,
    bribe_keyboard,
    declaration_keyboard,
    market_keyboard,
    private_menu,
)
from ..runtime import get_service
from ..service import GameError, GameService
from ..texts import render_hand, render_status

router = Router(name="common")


def svc(event) -> GameService:
    return get_service()


def goods_list(cards: list[str]) -> str:
    counter = Counter(cards)
    if not counter:
        return "нічого"
    return ", ".join(f"{GOODS[key].emoji} {GOODS[key].name} ×{count}" for key, count in counter.items())


@router.message(CommandStart())
async def start(message: Message) -> None:
    service = svc(message)
    await service.register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    if message.chat.type != "private":
        await message.answer(
            "Я працюю з таємними картками в особистих повідомленнях. "
            "Відкрий мене в ЛС і натисни /start."
        )
        return
    await message.answer(
        "🏰 <b>Шериф Ноттінгема</b>\n\n"
        "У групі створи партію командою /newgame, інші гравці приєднуються через /join. "
        "Рука, мішок і особисті пропозиції будуть тут, у приватному чаті.",
        reply_markup=private_menu(),
    )


@router.message(Command("hand"))
@router.callback_query(F.data == "menu:hand")
async def hand(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        game = await service.game_for_user(event.from_user.id)
        p = await service.player(game["id"], event.from_user.id)
        text = render_hand(loads(p["hand_json"]))
    except GameError as exc:
        text = f"⚠️ {exc}"
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=private_menu())
    else:
        await event.answer(text, reply_markup=private_menu())


@router.message(Command("market"))
@router.callback_query(F.data == "menu:market")
async def market(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        game = await service.game_for_user(event.from_user.id)
        if game["phase"] != "market":
            raise GameError("Зараз не етап «Торгівля».")
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] == event.from_user.id:
            raise GameError("Ти шериф цього раунду: під час «Торгівлі» лише спостерігаєш 👮")
        p = await service.player(game["id"], event.from_user.id)
        if p["resolved"]:
            raise GameError("Ти вже завершив торгівлю. Чекаємо на інших торговців.")
        hand_cards = loads(p["hand_json"])
        selected = loads(p["bag_json"])
        text = (
            "🛒 <b>Торгівля</b>\n"
            f"Обрано для скидання: <b>{len(selected)}/5</b>\n\n"
            "Можна скинути від 0 до 5 карток і добрати до шести. "
            "Скинуті товари будуть відкрито показані всім гравцям."
        )
        kb = market_keyboard(hand_cards, selected)
    except GameError as exc:
        text, kb = f"⚠️ {exc}", private_menu()
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("market:toggle:"))
async def market_toggle(callback: CallbackQuery) -> None:
    service = svc(callback)
    key = callback.data.rsplit(":", 1)[-1]
    try:
        p = await service.toggle_market_good(callback.from_user.id, key)
        hand_cards = loads(p["hand_json"])
        selected = loads(p["bag_json"])
        await callback.message.edit_text(
            "🛒 <b>Торгівля</b>\n"
            f"Обрано для скидання: <b>{len(selected)}/5</b>",
            reply_markup=market_keyboard(hand_cards, selected),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "market:clear")
async def market_clear(callback: CallbackQuery) -> None:
    service = svc(callback)
    try:
        p = await service.clear_market_selection(callback.from_user.id)
        await callback.message.edit_text(
            "🛒 <b>Торгівля</b>\nОбрано для скидання: <b>0/5</b>",
            reply_markup=market_keyboard(loads(p["hand_json"]), []),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "market:confirm")
async def market_confirm(callback: CallbackQuery) -> None:
    service = svc(callback)
    try:
        game = await service.game_for_user(callback.from_user.id)
        before = await service.player(game["id"], callback.from_user.id)
        discarded = loads(before["bag_json"])
        _, all_ready = await service.confirm_market(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ <b>Торгівлю завершено.</b> Скинуто карток: {len(discarded)}.\n"
            "Коли всі закінчать, почнеться завантаження товарів.",
            reply_markup=private_menu(),
        )

        if discarded:
            await callback.bot.send_message(
                game["chat_id"],
                f"🛒 <b>{callback.from_user.full_name}</b> скидає: {goods_list(discarded)}.",
            )
        else:
            await callback.bot.send_message(
                game["chat_id"],
                f"🛒 <b>{callback.from_user.full_name}</b> не скидає жодної картки.",
            )

        if all_ready:
            game = await service.game_for_user(callback.from_user.id)
            await callback.bot.send_message(
                game["chat_id"],
                "🎒 <b>Крок 2 — Завантаження товарів.</b>\n"
                "Усі торговці таємно кладуть у мішок від 1 до 5 карток. "
                "Після запечатування змінити вміст уже не можна.\n\n"
                "Відкрийте /bag у приватному чаті з ботом.",
            )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.message(Command("bag"))
@router.callback_query(F.data == "menu:bag")
async def bag(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        game = await service.game_for_user(event.from_user.id)
        if game["phase"] != "packing":
            if game["phase"] == "market":
                raise GameError("Спочатку заверши етап «Торгівля» через /market.")
            if game["phase"] in {"declaration", "inspection"}:
                raise GameError("Мішки цього раунду вже запечатано.")
            raise GameError("Зараз мішок збирати не можна.")
        p = await service.player(game["id"], event.from_user.id)
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] == event.from_user.id:
            raise GameError("У цьому раунді ти шериф 👮")
        if p["bag_locked"]:
            raise GameError(f"Мішок уже запечатано: {len(loads(p['bag_json']))} товарів.")
        hand_cards = loads(p["hand_json"])
        bag_cards = loads(p["bag_json"])
        text = (
            "🎒 <b>Завантаження товарів</b>\n"
            f"Обрано: <b>{len(bag_cards)}/5</b>\n\n"
            "Додай від 1 до 5 карток. Після натискання «Запечатати» "
            "повернути чи замінити товари вже не можна."
        )
        kb = bag_keyboard(hand_cards, bag_cards)
    except GameError as exc:
        text, kb = f"⚠️ {exc}", private_menu()
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("bag:toggle:"))
async def toggle_bag(callback: CallbackQuery) -> None:
    service = svc(callback)
    key = callback.data.rsplit(":", 1)[-1]
    try:
        p = await service.toggle_bag_good(callback.from_user.id, key)
        hand_cards = loads(p["hand_json"])
        bag_cards = loads(p["bag_json"])
        await callback.message.edit_text(
            "🎒 <b>Завантаження товарів</b>\n"
            f"Обрано: <b>{len(bag_cards)}/5</b>\n\n"
            f"У мішку зараз: {service.bag_summary(bag_cards)}",
            reply_markup=bag_keyboard(hand_cards, bag_cards),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "bag:clear")
async def clear_bag(callback: CallbackQuery) -> None:
    service = svc(callback)
    try:
        p = await service.clear_bag(callback.from_user.id)
        await callback.message.edit_text(
            "🎒 <b>Мішок очищено</b>\nОбрано: <b>0/5</b>",
            reply_markup=bag_keyboard(loads(p["hand_json"]), []),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "bag:lock")
async def lock_bag(callback: CallbackQuery) -> None:
    service = svc(callback)
    try:
        p, all_locked, first_declarer = await service.lock_bag(callback.from_user.id)
        bag_cards = loads(p["bag_json"])
        await callback.message.edit_text(
            "🔒 <b>Мішок запечатано.</b>\n\n"
            f"У ньому <b>{len(bag_cards)}</b> товарів. Вміст більше змінити не можна.\n"
            "Чекаємо, поки решта торговців також запечатають мішки.",
            reply_markup=private_menu(),
        )

        if all_locked and first_declarer:
            game = await service.game_for_user(callback.from_user.id)
            await callback.bot.send_message(
                game["chat_id"],
                "📜 <b>Крок 3 — Декларування.</b>\n"
                f"Починає <b>{first_declarer['full_name']}</b>, далі — за порядком навколо столу.\n"
                "Кількість карток у мішку називається точно, а вид можна назвати лише один — дозволений товар.",
            )
            try:
                await callback.bot.send_message(
                    first_declarer["user_id"],
                    "📜 <b>Твоя черга декларувати.</b>\n"
                    "Обери один вид дозволеного товару. Кількість карток бот зафіксує автоматично.",
                    reply_markup=declaration_keyboard(),
                )
            except Exception:
                pass
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("declare:"))
async def declare(callback: CallbackQuery) -> None:
    service = svc(callback)
    key = callback.data.split(":", 1)[1]
    try:
        p, all_declared, next_declarer = await service.declare(callback.from_user.id, key)
        game = await service.game_for_user(callback.from_user.id)
        bag_size = len(loads(p["bag_json"]))
        good = GOODS[key]
        declaration_text = f"{bag_size} × {good.emoji} {good.name}"

        await callback.message.edit_text(
            "📜 <b>Декларацію зафіксовано.</b>\n"
            f"Ти заявив: <b>{declaration_text}</b>.\n\n"
            "Змінити цю декларацію вже не можна. Під час переговорів можеш блефувати скільки завгодно 😏",
            reply_markup=private_menu(),
        )
        await callback.bot.send_message(
            game["chat_id"],
            f"📜 <b>{callback.from_user.full_name}</b> декларує: <b>{declaration_text}</b>.",
        )

        if next_declarer:
            try:
                await callback.bot.send_message(
                    next_declarer["user_id"],
                    "📜 <b>Тепер твоя черга декларувати.</b>",
                    reply_markup=declaration_keyboard(),
                )
            except Exception:
                pass
        elif all_declared:
            sheriff = await service.sheriff(game["id"])
            try:
                await callback.bot.send_message(
                    sheriff["user_id"],
                    "👮 <b>Усі торговці біля воріт.</b> Починається огляд.\n"
                    "Можеш вести переговори, приймати або ігнорувати хабарі й вирішувати долю кожного мішка через /inspect.",
                )
            except Exception:
                pass
            await callback.bot.send_message(
                game["chat_id"],
                "🔔 <b>Крок 4 — Огляд.</b>\n"
                "Усі декларації зафіксовано. Тепер можна торгуватися, погрожувати, блефувати й пропонувати хабарі 😏",
            )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.message(Command("bribe"))
async def bribe_command(message: Message) -> None:
    service = svc(message)
    args = (message.text or "").split(maxsplit=1)
    if len(args) == 2 and args[1].isdigit():
        try:
            offer = await service.set_bribe(message.from_user.id, int(args[1]))
            await message.answer(
                f"💰 Запропоновано шерифу: <b>{offer['coins']}</b> золотих.",
                reply_markup=private_menu(),
            )
        except GameError as exc:
            await message.answer(f"⚠️ {exc}")
        return
    await message.answer("💰 Обери розмір грошового хабара:", reply_markup=bribe_keyboard(0))


@router.callback_query(F.data == "menu:bribe")
async def bribe_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "💰 Обери розмір грошового хабара.\n"
        "Поки що бот автоматизує золото; товарами й майбутніми послугами можна домовлятися в загальному чаті.",
        reply_markup=bribe_keyboard(0),
    )


@router.callback_query(F.data.startswith("bribe:set:"))
async def bribe_set(callback: CallbackQuery) -> None:
    amount = int(callback.data.rsplit(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=bribe_keyboard(amount))
    await callback.answer()


@router.callback_query(F.data.startswith("bribe:confirm:"))
async def bribe_confirm(callback: CallbackQuery) -> None:
    service = svc(callback)
    amount = int(callback.data.rsplit(":", 1)[1])
    try:
        offer = await service.set_bribe(callback.from_user.id, amount)
        await callback.message.edit_text(
            f"💰 <b>Хабар запропоновано:</b> {amount} золотих.\n"
            "Золото спишеться лише якщо шериф явно прийме цей хабар і пропустить мішок.",
            reply_markup=private_menu(),
        )
        try:
            await callback.bot.send_message(
                offer["sheriff"]["user_id"],
                f"💰 {callback.from_user.full_name} пропонує <b>{amount}</b> золотих за пропуск мішка.",
            )
        except Exception:
            pass
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "menu:status")
async def private_status(callback: CallbackQuery) -> None:
    service = svc(callback)
    try:
        game = await service.game_for_user(callback.from_user.id)
        payload = await service.status_payload(game["id"])
        text = render_status(**payload)
    except GameError as exc:
        text = f"⚠️ {exc}"
    await callback.answer()
    await callback.message.answer(text, reply_markup=private_menu())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
