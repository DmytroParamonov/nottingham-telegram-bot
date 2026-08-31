from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..db import loads
from ..game_data import GOODS
from ..keyboards import bag_keyboard, bribe_keyboard, private_menu
from ..runtime import get_service
from ..service import GameError, GameService
from ..texts import render_hand, render_status

router = Router(name="common")


def svc(event) -> GameService:
    return get_service()


@router.message(CommandStart())
async def start(message: Message) -> None:
    service = svc(message)
    await service.register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    if message.chat.type != "private":
        await message.answer("Я работаю с секретными картами в личке. Открой меня в ЛС и нажми /start.")
        return
    await message.answer(
        "🏰 <b>Рынок Ноттингема</b>\n\n"
        "В группе создай партию командой /newgame, затем игроки входят через /join. "
        "Карты, мешок и взятки будут только здесь, в личке.",
        reply_markup=private_menu(),
    )


@router.message(Command("hand"))
@router.callback_query(F.data == "menu:hand")
async def hand(event: Message | CallbackQuery) -> None:
    service = svc(event)
    user = event.from_user
    try:
        game = await service.game_for_user(user.id)
        p = await service.player(game["id"], user.id)
        text = render_hand(loads(p["hand_json"]))
    except GameError as exc:
        text = f"⚠️ {exc}"
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=private_menu())
    else:
        await event.answer(text, reply_markup=private_menu())


@router.message(Command("bag"))
@router.callback_query(F.data == "menu:bag")
async def bag(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        game = await service.game_for_user(event.from_user.id)
        p = await service.player(game["id"], event.from_user.id)
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] == event.from_user.id:
            raise GameError("В этом раунде ты шериф 👮")
        if p["bag_locked"]:
            raise GameError(f"Мешок уже запечатан: {len(loads(p['bag_json']))} товара.")
        hand_cards = loads(p["hand_json"])
        bag_cards = loads(p["bag_json"])
        text = (
            "🎒 <b>Собери мешок</b>\n"
            f"Выбрано: <b>{len(bag_cards)}/5</b>\n\n"
            "Нажатие добавляет товар; повторяй, чтобы добавить несколько одинаковых. "
            "Когда готов — запечатай мешок."
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
            "🎒 <b>Собери мешок</b>\n"
            f"Выбрано: <b>{len(bag_cards)}/5</b>\n\n"
            f"Сейчас в мешке: {service.bag_summary(bag_cards)}",
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
            "🎒 <b>Мешок очищен</b>\nВыбрано: <b>0/5</b>",
            reply_markup=bag_keyboard(loads(p["hand_json"]), []),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "bag:lock")
async def lock_bag(callback: CallbackQuery) -> None:
    from ..keyboards import declaration_keyboard
    service = svc(callback)
    try:
        p = await service.lock_bag(callback.from_user.id)
        bag_cards = loads(p["bag_json"])
        await callback.message.edit_text(
            "🔒 <b>Перед воротами</b>\n\n"
            f"В мешке <b>{len(bag_cards)}</b> товара. Теперь объяви ОДИН легальный тип товара. "
            "Количество бот объявит честно автоматически.",
            reply_markup=declaration_keyboard(),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("declare:"))
async def declare(callback: CallbackQuery) -> None:
    service = svc(callback)
    key = callback.data.split(":", 1)[1]
    try:
        p, all_ready = await service.declare(callback.from_user.id, key)
        bag_size = len(loads(p["bag_json"]))
        good = GOODS[key]
        await callback.message.edit_text(
            f"📜 <b>Декларация подана</b>\n"
            f"Ты заявил: <b>{bag_size} × {good.emoji} {good.name}</b>.\n\n"
            "Теперь можешь торговаться с шерифом в общем чате или предложить официальную денежную взятку: /bribe 5",
            reply_markup=private_menu(),
        )
        if all_ready:
            game = await service.game_for_user(callback.from_user.id)
            sheriff = await service.sheriff(game["id"])
            try:
                await callback.bot.send_message(
                    sheriff["user_id"],
                    "👮 <b>Все торговцы у ворот.</b> Пора решать, кого пропустить, а кого обыскать.\nИспользуй /inspect.",
                )
            except Exception:
                pass
            await callback.bot.send_message(
                game["chat_id"],
                "🔔 <b>Все декларации поданы!</b>\nШериф начинает досмотр. Торгуйтесь, пока не поздно 😏",
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
            await message.answer(f"💰 Предложено шерифу: <b>{offer['coins']}</b> золотых.", reply_markup=private_menu())
        except GameError as exc:
            await message.answer(f"⚠️ {exc}")
        return
    await message.answer("💰 Выбери размер денежной взятки:", reply_markup=bribe_keyboard(0))


@router.callback_query(F.data == "menu:bribe")
async def bribe_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("💰 Выбери размер денежной взятки:", reply_markup=bribe_keyboard(0))


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
            f"💰 <b>Взятка предложена:</b> {amount} золотых.\n"
            "Она спишется только если шериф пропустит мешок без проверки.",
            reply_markup=private_menu(),
        )
        try:
            await callback.bot.send_message(
                offer["sheriff"]["user_id"],
                f"💰 {callback.from_user.full_name} предлагает <b>{amount}</b> золотых за пропуск мешка.",
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
