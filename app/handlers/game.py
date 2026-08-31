from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db import loads
from ..game_data import GOODS
from ..keyboards import private_menu, sheriff_decision_keyboard, sheriff_keyboard
from ..runtime import get_service
from ..service import GameError, GameService
from ..texts import render_lobby, render_scoreboard, render_status

router = Router(name="game")


def svc(event) -> GameService:
    return get_service()


def legal_goods_text(cards: list[str]) -> str:
    counter = Counter(cards)
    if not counter:
        return "немає"
    return ", ".join(
        f"{GOODS[key].emoji} {GOODS[key].name} ×{count}"
        for key, count in counter.items()
    )


async def ensure_registered(message: Message) -> None:
    await svc(message).register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )


def group_only(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


@router.message(Command("newgame"))
async def new_game(message: Message) -> None:
    if not group_only(message):
        await message.answer("Створюй партію в груповому чаті.")
        return
    await ensure_registered(message)
    service = svc(message)
    try:
        game = await service.create_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        await message.answer(render_lobby(players, game["owner_id"]))
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("join"))
async def join(message: Message) -> None:
    if not group_only(message):
        return
    await ensure_registered(message)
    service = svc(message)
    try:
        game = await service.join_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        await message.answer(render_lobby(players, game["owner_id"]))
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("leave"))
async def leave(message: Message) -> None:
    if not group_only(message):
        return
    service = svc(message)
    try:
        await service.leave_lobby(message.chat.id, message.from_user.id)
        game = await service.active_game(message.chat.id)
        players = await service.players(game["id"])
        await message.answer(render_lobby(players, game["owner_id"]))
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("cancelgame"))
async def cancel(message: Message) -> None:
    if not group_only(message):
        return
    try:
        await svc(message).cancel_game(message.chat.id, message.from_user.id)
        await message.answer("🧹 Партію скасовано. Нову можна створити через /newgame.")
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("players"))
async def players_cmd(message: Message) -> None:
    if not group_only(message):
        return
    service = svc(message)
    game = await service.active_game(message.chat.id)
    if not game:
        await message.answer("Активної партії немає.")
        return
    players = await service.players(game["id"])
    await message.answer(render_lobby(players, game["owner_id"]))


@router.message(Command("begin"))
async def begin(message: Message) -> None:
    if not group_only(message):
        return
    service = svc(message)
    try:
        lobby = await service.active_game(message.chat.id)
        if not lobby or lobby["status"] != "lobby":
            raise GameError("Відкритого лобі немає.")
        lobby_players = await service.players(lobby["id"])

        dm_failed = []
        for p in lobby_players:
            try:
                await message.bot.send_message(
                    p["user_id"],
                    "🎟 <b>Зв’язок перевірено.</b> Партія зараз почнеться.",
                )
            except Exception:
                dm_failed.append(p["full_name"])
        if dm_failed:
            await message.answer(
                "⛔ <b>Партію поки не запускаю.</b> Не можу написати в особисті повідомлення: "
                + ", ".join(dm_failed)
                + ".\nЇм потрібно відкрити бота, натиснути /start і потім повторити /begin."
            )
            return

        game = await service.start_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        sheriff = await service.sheriff(game["id"])
        for p in players:
            if p["user_id"] == sheriff["user_id"]:
                text = (
                    "👮 <b>Ти перший шериф.</b>\n\n"
                    "На кроці «Торгівля» ти не змінюєш руку. "
                    "Відкрий /market і <b>обери першого торговця</b>; далі хід піде за годинниковою стрілкою."
                )
            else:
                text = (
                    "🎲 <b>Партія почалася!</b>\n"
                    "У тебе 6 карток. Зараз крок «Торгівля»: дочекайся, поки шериф визначить першого гравця. "
                    "Коли настане твій хід, бот напише тобі."
                )
            await message.bot.send_message(p["user_id"], text, reply_markup=private_menu())

        player_count = len(players)
        rounds_per_sheriff = 3 if player_count == 3 else 2
        await message.answer(
            "🚪 <b>Ворота Ноттінгема відчинено!</b>\n"
            f"Раунд 1. Шериф: <b>{sheriff['full_name']}</b>.\n"
            f"Гравців: <b>{player_count}</b> · кожен побуде шерифом <b>{rounds_per_sheriff}</b> раз(и).\n\n"
            "🛒 <b>Крок 1 — Торгівля.</b> Шериф спочатку обирає першого торговця через /market. "
            "Потім торговці ходять за годинниковою стрілкою, відкрито скидаючи 0–5 карток."
        )
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("status"))
async def status(message: Message) -> None:
    service = svc(message)
    try:
        if group_only(message):
            game = await service.active_game(message.chat.id)
            if not game:
                raise GameError("Активної партії немає.")
        else:
            game = await service.game_for_user(message.from_user.id)
        payload = await service.status_payload(game["id"])
        await message.answer(render_status(**payload))
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


async def render_sheriff_panel(event: Message | CallbackQuery) -> None:
    service = svc(event)
    try:
        game = await service.game_for_user(event.from_user.id)
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] != event.from_user.id:
            raise GameError("Зараз ти не шериф.")
        if game["phase"] != "inspection":
            raise GameError("Огляд ще не почався — спершу всі мають подати декларації.")
        merchants = await service.merchant_rows(game["id"])
        bribes = {}
        for m in merchants:
            offer = await service.bribe(game["id"], m["user_id"])
            bribes[m["user_id"]] = (
                int(offer["coins"]) if offer and offer["status"] == "offered" else 0
            )
        text = (
            "👮 <b>Пост шерифа</b>\n"
            "Ти можеш оглянути будь-яку кількість мішків у будь-якому порядку або не оглядати жодного.\n\n"
            "Обери торговця:"
        )
        kb = sheriff_keyboard(merchants, bribes)
    except GameError as exc:
        text, kb = f"⚠️ {exc}", private_menu()
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.message(Command("inspect"))
async def inspect_cmd(message: Message) -> None:
    await render_sheriff_panel(message)


@router.callback_query(F.data == "sheriff:list")
async def sheriff_list(callback: CallbackQuery) -> None:
    await render_sheriff_panel(callback)


@router.callback_query(F.data.startswith("sheriff:merchant:"))
async def sheriff_merchant(callback: CallbackQuery) -> None:
    service = svc(callback)
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        game = await service.game_for_user(callback.from_user.id)
        sheriff = await service.sheriff(game["id"])
        if sheriff["user_id"] != callback.from_user.id:
            raise GameError("Зараз ти не шериф.")
        merchant = await service.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Цей торговець уже пройшов ворота.")
        bag_size = len(loads(merchant["bag_json"]))
        good = GOODS[merchant["declared_good"]]
        offer = await service.bribe(game["id"], merchant_id)
        bribe = int(offer["coins"]) if offer and offer["status"] == "offered" else 0
        await callback.message.answer(
            f"🧳 <b>{merchant['full_name']}</b>\n"
            f"Задекларовано: <b>{bag_size} × {good.emoji} {good.name}</b>\n"
            f"Запропонований грошовий хабар: <b>💰 {bribe}</b>\n\n"
            "Що робимо?",
            reply_markup=sheriff_decision_keyboard(merchant_id, bribe),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


async def announce_advance(bot, service: GameService, game_id: int, advanced: dict | None) -> None:
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
        f"Новий шериф: <b>{sheriff['full_name']}</b>.\n\n"
        "🛒 Починається крок «Торгівля». Новий шериф має відкрити /market і обрати першого торговця.",
    )
    try:
        await bot.send_message(
            sheriff["user_id"],
            "👮 <b>Тепер ти шериф.</b> Відкрий /market і обери першого торговця. "
            "Сам ти під час «Торгівлі» руку не змінюєш.",
            reply_markup=private_menu(),
        )
    except Exception:
        pass


async def resolve_pass(
    callback: CallbackQuery,
    merchant_id: int,
    *,
    accept_bribe: bool,
) -> None:
    service = svc(callback)
    game = await service.game_for_user(callback.from_user.id)
    merchant = await service.player(game["id"], merchant_id)
    result = await service.pass_merchant(
        callback.from_user.id,
        merchant_id,
        accept_bribe=accept_bribe,
    )
    suffix = (
        f"\nПрийнятий хабар: <b>💰 {result['bribe']}</b>."
        if result["bribe"]
        else "\nШериф не взяв грошового хабара."
    )
    await callback.message.edit_text(
        f"✅ <b>{merchant['full_name']} проходить без огляду.</b>{suffix}"
    )
    await callback.bot.send_message(
        game["chat_id"],
        f"✅ Шериф пропустив <b>{merchant['full_name']}</b> без огляду.\n"
        f"Дозволені товари: <b>{legal_goods_text(result['legal_cards'])}</b>.\n"
        f"Контрабанда: <b>{result['contraband_count']}</b> карт. Вид залишається таємним.",
    )
    await callback.answer()
    await announce_advance(callback.bot, service, game["id"], result["advanced"])


@router.callback_query(F.data.startswith("sheriff:pass:"))
async def sheriff_pass(callback: CallbackQuery) -> None:
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await resolve_pass(callback, merchant_id, accept_bribe=False)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("sheriff:accept:"))
async def sheriff_accept_bribe(callback: CallbackQuery) -> None:
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await resolve_pass(callback, merchant_id, accept_bribe=True)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("sheriff:inspect:"))
async def sheriff_inspect(callback: CallbackQuery) -> None:
    service = svc(callback)
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        game = await service.game_for_user(callback.from_user.id)
        merchant = await service.player(game["id"], merchant_id)
        outcome = await service.inspect_merchant(callback.from_user.id, merchant_id)
        result = outcome["result"]
        bag = outcome["bag"]
        contents = ", ".join(GOODS[key].label for key in bag)
        settlement = outcome["settlement"]
        goods_payment = ""
        if settlement.goods_paid:
            goods_payment = (
                "\nОплата товарами через нестачу золота: "
                + ", ".join(GOODS[key].label for key in settlement.goods_paid)
            )
        if settlement.forgiven:
            goods_payment += f"\nНесплачений залишок {settlement.forgiven} вважається погашеним."

        if result.truthful:
            verdict = (
                "😇 <b>ТОРГОВЕЦЬ СКАЗАВ ПРАВДУ!</b>\n"
                f"Шериф має сплатити штраф на суму <b>💰 {outcome['amount_due']}</b>."
                f"{goods_payment}"
            )
        else:
            confiscated = ", ".join(GOODS[key].label for key in result.confiscated)
            verdict = (
                "🚨 <b>БРЕХНЮ ВИКРИТО!</b>\n"
                f"Конфісковано: {confiscated}\n"
                f"Торговець має сплатити штраф на суму <b>💰 {outcome['amount_due']}</b>."
                f"{goods_payment}"
            )
        text = f"🔍 <b>Мішок {merchant['full_name']}</b>\n{contents}\n\n{verdict}"
        await callback.message.edit_text(text)
        await callback.bot.send_message(game["chat_id"], text)
        await callback.answer()
        await announce_advance(callback.bot, service, game["id"], outcome["advanced"])
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)
