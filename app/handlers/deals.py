from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..deal_texts import payment_result_text_fantasy, render_deal_fantasy
from ..deals import (
    accept_deal,
    adjust_gold,
    adjust_good,
    draft,
    incoming_offers,
    offer_draft,
    reject_deal,
    reset_draft,
    set_followup_inspection,
    set_future_promise,
    set_target_action,
)
from ..game_data import GOODS
from ..keyboards import (
    deal_builder_keyboard,
    deal_followup_keyboard,
    deal_goods_keyboard,
    deal_offer_keyboard,
    private_menu,
)
from ..runtime import get_service
from ..service import GameError, GameService
from ..texts import render_scoreboard

router = Router(name="deals")


def svc(event) -> GameService:
    return get_service()


def _is_private(event: Message | CallbackQuery) -> bool:
    message = event.message if isinstance(event, CallbackQuery) else event
    return message.chat.type == "private"


def _goods_cards_text(cards: list[str]) -> str:
    if not cards:
        return "—"
    counter = Counter(cards)
    return ", ".join(
        f"{GOODS[key].emoji} {GOODS[key].name} ×{count}"
        for key, count in counter.items()
    )


async def _show_builder(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        if not _is_private(event):
            raise GameError("Таємні угоди з вартою складаються в особистому чаті з ботом.")
        game = await service.game_for_user(event.from_user.id)
        if game["phase"] != "inspection":
            raise GameError("Домовлятися з вартою можна під час етапу огляду.")
        sheriff = await service.sheriff(game["id"])

        if sheriff["user_id"] == event.from_user.id:
            offers = await incoming_offers(service, event.from_user.id)
            if not offers:
                text = (
                    "🛡 <b>Угоди міської варти</b>\n\n"
                    "Формальних пропозицій поки немає. Купці можуть торгуватися вголос, "
                    "а коли хтось зафіксує умови — вони з'являться тут."
                )
                kb = private_menu()
                if isinstance(event, CallbackQuery):
                    await event.answer()
                    await event.message.answer(text, reply_markup=kb)
                else:
                    await event.answer(text, reply_markup=kb)
                return

            if isinstance(event, CallbackQuery):
                await event.answer()
            header = (
                "🛡 <b>Формальні пропозиції командиру варти</b>\n"
                "Якщо приймеш угоду, бот одразу виконає її обов'язкові умови."
            )
            if isinstance(event, CallbackQuery):
                await event.message.answer(header)
            else:
                await event.answer(header)
            for row in offers:
                text = await render_deal_fantasy(service, row)
                if isinstance(event, CallbackQuery):
                    await event.message.answer(text, reply_markup=deal_offer_keyboard(row["id"]))
                else:
                    await event.bot.send_message(event.chat.id, text, reply_markup=deal_offer_keyboard(row["id"]))
            return

        row = await draft(service, event.from_user.id)
        assert row is not None
        merchants = await service.merchant_rows(game["id"])
        text = (
            (await render_deal_fantasy(service, row))
            + "\n\n<b>Збери фінальні умови та натисни «Надіслати варті».</b>\n"
            "Товарами з лавки й вантажу можна блефувати. Карти, які лишилися в руці, як хабар не використовуються."
        )
        kb = deal_builder_keyboard(merchants, row)
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
    except GameError as exc:
        text = f"⚠️ {exc}"
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text, reply_markup=private_menu())
        else:
            await event.answer(text, reply_markup=private_menu())


@router.message(Command("deal"))
async def deal_command(message: Message) -> None:
    await _show_builder(message)


@router.callback_query(F.data == "menu:deals")
async def deals_menu(callback: CallbackQuery) -> None:
    await _show_builder(callback)


@router.callback_query(F.data.startswith("deal:target:"))
async def deal_target(callback: CallbackQuery) -> None:
    try:
        _, _, action, raw_id = callback.data.split(":", 3)
        await set_target_action(svc(callback), callback.from_user.id, int(raw_id), action)
        await callback.answer("Умову змінено")
        await _show_builder(callback)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("deal:gold:"))
async def deal_gold(callback: CallbackQuery) -> None:
    try:
        delta = int(callback.data.rsplit(":", 1)[1])
        await adjust_gold(svc(callback), callback.from_user.id, delta)
        await callback.answer()
        await _show_builder(callback)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("deal:goods:"))
async def deal_goods_menu(callback: CallbackQuery) -> None:
    source = callback.data.rsplit(":", 1)[1]
    try:
        row = await draft(svc(callback), callback.from_user.id)
        assert row is not None
        if source == "bag" and not (
            row["target_id"] == callback.from_user.id and row["action"] == "pass"
        ):
            raise GameError(
                "Товари з вантажу можна обіцяти лише коли ти купуєш пропуск власної повозки."
            )
        await callback.answer()
        await callback.message.answer(
            "🏪 <b>Товари з лавки</b>"
            if source == "stand"
            else "🛞 <b>Товари з вантажу</b>\nМожна блефувати про кількість і вид.",
            reply_markup=deal_goods_keyboard(source, row),
        )
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("deal:good:"))
async def deal_good_adjust(callback: CallbackQuery) -> None:
    try:
        _, _, source, key, raw_delta = callback.data.split(":", 4)
        row = await adjust_good(
            svc(callback),
            callback.from_user.id,
            source,
            key,
            int(raw_delta),
        )
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=deal_goods_keyboard(source, row))
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "deal:followup")
async def deal_followup_menu(callback: CallbackQuery) -> None:
    try:
        service = svc(callback)
        game = await service.game_for_user(callback.from_user.id)
        row = await draft(service, callback.from_user.id)
        assert row is not None
        merchants = await service.merchant_rows(game["id"])
        await callback.answer()
        await callback.message.answer(
            "📌 <b>Обов'язковий додатковий обшук</b>\n"
            "Якщо командир варти прийме угоду, ця повозка буде обшукана в цьому ж раунді незалежно від інших хабарів.",
            reply_markup=deal_followup_keyboard(merchants, row),
        )
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("deal:followup:set:"))
async def deal_followup_set(callback: CallbackQuery) -> None:
    try:
        raw = int(callback.data.rsplit(":", 1)[1])
        await set_followup_inspection(
            svc(callback),
            callback.from_user.id,
            None if raw == 0 else raw,
        )
        await callback.answer("Умову збережено")
        await _show_builder(callback)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "deal:promise_help")
async def deal_promise_help(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "💭 <b>Майбутня обіцянка</b>\n\n"
        "Напиши мені окремим повідомленням, наприклад:\n"
        "<code>/promise Не обшукуватиму твою повозку, коли очолю варту</code>\n\n"
        "Щоб прибрати обіцянку: <code>/promise -</code>\n"
        "⚠️ Майбутня обіцянка не є обов'язковою. У Новіграді слова часто коштують дешевше за крони."
    )


@router.message(Command("promise"))
async def promise_command(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Додай обіцянку в особистому чаті з ботом.")
        return
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) == 1:
        await message.answer("Напиши: <code>/promise текст обіцянки</code>. Для очищення: <code>/promise -</code>.")
        return
    text = raw[1].strip()
    if text == "-":
        text = ""
    try:
        await set_future_promise(svc(message), message.from_user.id, text)
        await message.answer("💭 Обіцянку збережено.", reply_markup=private_menu())
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.callback_query(F.data == "deal:reset")
async def deal_reset(callback: CallbackQuery) -> None:
    try:
        await reset_draft(svc(callback), callback.from_user.id)
        await callback.answer("Чернетку очищено")
        await _show_builder(callback)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "deal:offer")
async def deal_offer(callback: CallbackQuery) -> None:
    try:
        service = svc(callback)
        row = await offer_draft(service, callback.from_user.id)
        text = await render_deal_fantasy(service, row)
        sheriff = await service.sheriff(row["game_id"])
        await callback.message.edit_text(
            "📤 <b>Фінальну пропозицію передано командиру варти.</b>\n\n" + text,
            reply_markup=private_menu(),
        )
        await callback.bot.send_message(
            sheriff["user_id"],
            "🔔 <b>Нова формальна угода біля брами.</b>\n"
            "Якщо натиснеш «УГОДА — прийняти», бот одразу виконає всі обов'язкові умови.\n\n"
            + text,
            reply_markup=deal_offer_keyboard(row["id"]),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


async def _inspection_result_text(service: GameService, game_id: int, target_id: int, outcome: dict) -> str:
    merchant = await service.player(game_id, target_id)
    result = outcome["result"]
    contents = ", ".join(GOODS[key].label for key in outcome["bag"])
    settlement = outcome["settlement"]
    extras = ""
    if settlement.goods_paid:
        extras += "\nБорг покрито товарами: " + _goods_cards_text(list(settlement.goods_paid))
    if settlement.forgiven:
        extras += f"\nНесплачений залишок {settlement.forgiven} крон вважається погашеним."
    if result.truthful:
        verdict = (
            f"😇 Купець не брехав. Варта платить йому <b>{outcome['amount_due']} крон</b> за даремний обшук."
        )
    else:
        verdict = (
            "🚨 Контрабанду викрито. Конфісковано: "
            + _goods_cards_text(list(result.confiscated))
            + f". Штраф: <b>{outcome['amount_due']} крон</b>."
        )
    return f"🔍 <b>Обшук повозки · {merchant['full_name']}</b>\n{contents}\n\n{verdict}{extras}"


async def _pass_result_text(service: GameService, game_id: int, target_id: int, outcome: dict) -> str:
    merchant = await service.player(game_id, target_id)
    legal = _goods_cards_text(outcome["legal_cards"])
    return (
        f"✅ <b>{merchant['full_name']} проходить крізь браму без обшуку.</b>\n"
        f"Дозволені товари: {legal}.\n"
        f"Контрабанда: <b>{outcome['contraband_count']}</b> карт(ок). Її вид лишається таємним."
    )


async def _announce_advance(bot, service: GameService, game_id: int, advanced: dict | None) -> None:
    if not advanced:
        return
    game = await service.game(game_id)
    if advanced["finished"]:
        rows = await service.scoreboard(game_id)
        await bot.send_message(game["chat_id"], render_scoreboard(rows))
        return
    sheriff = await service.sheriff(game_id)
    await bot.send_message(
        game["chat_id"],
        f"🔄 <b>Раунд {game['round_no']}</b>\n"
        f"Новий командир варти: <b>{sheriff['full_name']}</b>.\n"
        "🛒 Починається торг на ринку. Новий командир відкриває /market і обирає першого купця."
    )
    try:
        await bot.send_message(
            sheriff["user_id"],
            "🛡 Ти командир варти. Відкрий /market і обери, хто торгує першим.",
            reply_markup=private_menu(),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("deal:reject:"))
async def deal_reject(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.rsplit(":", 1)[1])
    try:
        service = svc(callback)
        row = await reject_deal(service, callback.from_user.id, deal_id)
        proposer = await service.player(row["game_id"], row["proposer_id"])
        await callback.message.edit_text("❌ <b>Варта відхилила угоду.</b>")
        try:
            await callback.bot.send_message(
                proposer["user_id"],
                f"❌ Командир варти відхилив твою угоду #{deal_id}. Можеш зібрати нову через /deal.",
                reply_markup=private_menu(),
            )
        except Exception:
            pass
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("deal:accept:"))
async def deal_accept(callback: CallbackQuery) -> None:
    deal_id = int(callback.data.rsplit(":", 1)[1])
    try:
        service = svc(callback)
        before = await service.db.fetchone("SELECT * FROM deals WHERE id=?", (deal_id,))
        if not before:
            raise GameError("Угоду не знайдено.")
        terms = await render_deal_fantasy(service, before)
        outcome = await accept_deal(service, callback.from_user.id, deal_id)
        row = outcome["deal"]
        game_id = row["game_id"]
        game = await service.game(game_id)

        await callback.message.edit_text(
            "🤝 <b>УГОДУ ПРИЙНЯТО.</b> Варта дотримується зафіксованих умов."
        )
        await callback.bot.send_message(
            game["chat_id"],
            "🤝 <b>УГОДА БІЛЯ БРАМИ!</b>\n\n"
            + terms
            + "\n\n"
            + payment_result_text_fantasy(outcome),
        )

        if row["action"] == "pass":
            await callback.bot.send_message(
                game["chat_id"],
                await _pass_result_text(service, game_id, row["target_id"], outcome["primary"]),
            )
        else:
            await callback.bot.send_message(
                game["chat_id"],
                await _inspection_result_text(service, game_id, row["target_id"], outcome["primary"]),
            )

        if outcome["followup"] is not None:
            await callback.bot.send_message(
                game["chat_id"],
                "📌 <b>Додаткова умова угоди:</b>\n"
                + await _inspection_result_text(
                    service,
                    game_id,
                    row["followup_inspect_id"],
                    outcome["followup"],
                ),
            )

        proposer = await service.player(game_id, row["proposer_id"])
        try:
            await callback.bot.send_message(
                proposer["user_id"],
                f"🤝 Командир варти прийняв угоду #{deal_id}.\n"
                + payment_result_text_fantasy(outcome),
                reply_markup=private_menu(),
            )
        except Exception:
            pass

        await callback.answer()
        await _announce_advance(callback.bot, service, game_id, outcome["advanced"])
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)
