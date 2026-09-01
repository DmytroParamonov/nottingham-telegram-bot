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
    market_first_keyboard,
    market_keyboard,
    private_menu,
)
from ..market_order import (
    choose_first_trader,
    current_market_trader,
    ensure_market_turn,
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
    return ", ".join(
        f"{GOODS[key].emoji} {GOODS[key].name} ×{count}"
        for key, count in counter.items()
    )


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
            "Таємні товари й угоди приходять в особисті повідомлення. "
            "Відкрий мене в ЛС і натисни /start."
        )
        return
    await message.answer(
        "🐺 <b>Брама Новіграда</b>\n\n"
        "У групі збери купців через /newgame, інші приєднаються через /join. "
        "Товари, вантаж і приватні пропозиції варті будуть тут.",
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
            raise GameError("Зараз не етап «Торг на ринку».")
        sheriff = await service.sheriff(game["id"])

        if sheriff["user_id"] == event.from_user.id:
            if game.get("market_start_seat") is None:
                merchants = await service.merchant_rows(game["id"])
                text = (
                    "🛡 <b>Торг на ринку: вибір першого купця</b>\n\n"
                    "Командир варти обирає, хто торгує першим. "
                    "Після нього хід піде за годинниковою стрілкою."
                )
                kb = market_first_keyboard(merchants)
            else:
                current = await current_market_trader(service, game["id"])
                if current:
                    text = (
                        "🛡 <b>Ринок шумить.</b>\n"
                        f"Зараз торгує: <b>{current['full_name']}</b>.\n"
                        "Спостерігай, які товари він відкрито скидає."
                    )
                else:
                    text = "🛡 Торг цього раунду вже завершено."
                kb = private_menu()
        else:
            p = await ensure_market_turn(service, event.from_user.id)
            hand_cards = loads(p["hand_json"])
            selected = loads(p["bag_json"])
            text = (
                "🛒 <b>Торг на ринку — твій хід</b>\n"
                f"Обрано для скидання: <b>{len(selected)}/5</b>\n\n"
                "Можеш скинути 0–5 товарів і добрати руку до шести. "
                "Скинуті товари всі побачать — варта теж дивиться."
            )
            kb = market_keyboard(hand_cards, selected)
    except GameError as exc:
        text, kb = f"⚠️ {exc}", private_menu()

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("market:first:"))
async def market_first(callback: CallbackQuery) -> None:
    service = svc(callback)
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        merchant = await choose_first_trader(service, callback.from_user.id, merchant_id)
        game = await service.game_for_user(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ Першим торгує <b>{merchant['full_name']}</b>. "
            "Далі — за годинниковою стрілкою."
        )
        await callback.bot.send_message(
            game["chat_id"],
            f"🛒 Командир варти обрав першого купця: <b>{merchant['full_name']}</b>. "
            "Після нього торгуємо за годинниковою стрілкою.",
        )
        try:
            await callback.bot.send_message(
                merchant["user_id"],
                "🛒 <b>Твій хід на ринку.</b> Відкрий /market, скинь 0–5 товарів і підтвердь хід.",
                reply_markup=private_menu(),
            )
        except Exception:
            pass
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("market:toggle:"))
async def market_toggle(callback: CallbackQuery) -> None:
    service = svc(callback)
    key = callback.data.rsplit(":", 1)[-1]
    try:
        await ensure_market_turn(service, callback.from_user.id)
        p = await service.toggle_market_good(callback.from_user.id, key)
        hand_cards = loads(p["hand_json"])
        selected = loads(p["bag_json"])
        await callback.message.edit_text(
            "🛒 <b>Торг на ринку — твій хід</b>\n"
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
        await ensure_market_turn(service, callback.from_user.id)
        p = await service.clear_market_selection(callback.from_user.id)
        await callback.message.edit_text(
            "🛒 <b>Торг на ринку — твій хід</b>\nОбрано для скидання: <b>0/5</b>",
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
        await ensure_market_turn(service, callback.from_user.id)
        before = await service.player(game["id"], callback.from_user.id)
        discarded = loads(before["bag_json"])
        _, all_ready = await service.confirm_market(callback.from_user.id)

        await callback.message.edit_text(
            f"✅ <b>Торг завершено.</b> Скинуто товарів: {len(discarded)}.",
            reply_markup=private_menu(),
        )
        if discarded:
            await callback.bot.send_message(
                game["chat_id"],
                f"🛒 <b>{callback.from_user.full_name}</b> скидає на ринку: {goods_list(discarded)}.",
            )
        else:
            await callback.bot.send_message(
                game["chat_id"],
                f"🛒 <b>{callback.from_user.full_name}</b> нічого не скидає.",
            )

        if all_ready:
            await callback.bot.send_message(
                game["chat_id"],
                "🛞 <b>Крок 2 — Завантаження возів.</b>\n"
                "Усі купці таємно кладуть у вантаж від 1 до 5 товарів. "
                "Після запечатування змінити його вже не можна.\n\n"
                "Відкрийте /bag у приватному чаті з ботом."
            )
        else:
            next_trader = await current_market_trader(service, game["id"])
            if next_trader:
                await callback.bot.send_message(
                    game["chat_id"],
                    f"➡️ Наступним торгує <b>{next_trader['full_name']}</b>.",
                )
                try:
                    await callback.bot.send_message(
                        next_trader["user_id"],
                        "🛒 <b>Тепер твій хід на ринку.</b> Відкрий /market.",
                        reply_markup=private_menu(),
                    )
                except Exception:
                    pass
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
                raise GameError("Спочатку заверши торг на ринку.")
            if game["phase"] in {"declaration", "inspection"}:
                raise GameError("Вантажі цього раунду вже запечатано.")
            raise GameError("Зараз вантаж готувати не можна.")
        p = await service.player(game["id"], event.from_user.id)
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] == event.from_user.id:
            raise GameError("У цьому раунді ти командир варти 🛡")
        if p["bag_locked"]:
            raise GameError(f"Вантаж уже запечатано: {len(loads(p['bag_json']))} товарів.")
        hand_cards = loads(p["hand_json"])
        bag_cards = loads(p["bag_json"])
        text = (
            "🛞 <b>Завантаження повозки</b>\n"
            f"Обрано: <b>{len(bag_cards)}/5</b>\n\n"
            "Додай від 1 до 5 товарів. Можеш змішати дозволене й контрабанду. "
            "Після «Запечатати вантаж» повернути чи замінити товар уже не можна."
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
            "🛞 <b>Завантаження повозки</b>\n"
            f"Обрано: <b>{len(bag_cards)}/5</b>\n\n"
            f"У вантажі зараз: {service.bag_summary(bag_cards)}",
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
            "🛞 <b>Вантаж очищено</b>\nОбрано: <b>0/5</b>",
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
            "🔒 <b>Вантаж запечатано.</b>\n\n"
            f"У повозці <b>{len(bag_cards)}</b> товарів. Вміст більше змінити не можна.\n"
            "Чекаємо, поки решта купців також запечатають вантаж."
        , reply_markup=private_menu())

        if all_locked and first_declarer:
            game = await service.game_for_user(callback.from_user.id)
            await callback.bot.send_message(
                game["chat_id"],
                "📜 <b>Крок 3 — Декларація біля брами.</b>\n"
                f"Починає <b>{first_declarer['full_name']}</b>, далі — за годинниковою стрілкою.\n"
                "Кількість товарів називається точно. Вид заявляється лише один і лише дозволений."
            )
            try:
                await callback.bot.send_message(
                    first_declarer["user_id"],
                    "📜 <b>Твоя черга говорити з вартою.</b>\n"
                    "Обери один дозволений товар. Кількість вантажу бот зафіксує автоматично.",
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
            "📜 <b>Слова перед вартою зафіксовано.</b>\n"
            f"Ти заявив: <b>{declaration_text}</b>.\n\n"
            "Змінити декларацію вже не можна. А от переконувати варту, торгуватися й блефувати — можна 😏",
            reply_markup=private_menu(),
        )
        await callback.bot.send_message(
            game["chat_id"],
            f"📜 <b>{callback.from_user.full_name}</b> заявляє варті: <b>{declaration_text}</b>.",
        )

        if next_declarer:
            try:
                await callback.bot.send_message(
                    next_declarer["user_id"],
                    "📜 <b>Тепер твоя черга говорити з вартою.</b>",
                    reply_markup=declaration_keyboard(),
                )
            except Exception:
                pass
        elif all_declared:
            sheriff = await service.sheriff(game["id"])
            try:
                await callback.bot.send_message(
                    sheriff["user_id"],
                    "🛡 <b>Усі купці біля брами.</b> Починається огляд.\n"
                    "Можеш домовлятися, приймати або ігнорувати хабарі й вирішувати долю кожної повозки через /inspect."
                )
            except Exception:
                pass
            await callback.bot.send_message(
                game["chat_id"],
                "🔔 <b>Крок 4 — Огляд вартою.</b>\n"
                "Усі декларації зафіксовано. Тепер можна торгуватися, погрожувати, блефувати й пропонувати хабарі 😏"
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
                f"🪙 Запропоновано командиру варти: <b>{offer['coins']}</b> крон.",
                reply_markup=private_menu(),
            )
        except GameError as exc:
            await message.answer(f"⚠️ {exc}")
        return
    await message.answer("🪙 Обери розмір хабара в кронах:", reply_markup=bribe_keyboard(0))


@router.callback_query(F.data == "menu:bribe")
async def bribe_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "🪙 Обери розмір грошового хабара.\n"
        "Крони бот перерахує автоматично. Для товарів, умов і складних домовленостей відкрий «Угоди з вартою».",
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
            f"🪙 <b>Хабар запропоновано:</b> {amount} крон.\n"
            "Крони спишуться лише якщо командир варти явно прийме хабар і пропустить твою повозку.",
            reply_markup=private_menu(),
        )
        try:
            await callback.bot.send_message(
                offer["sheriff"]["user_id"],
                f"🪙 {callback.from_user.full_name} пропонує <b>{amount}</b> крон за пропуск повозки.",
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
