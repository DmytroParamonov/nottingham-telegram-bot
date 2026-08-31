from __future__ import annotations

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
        await message.answer("Создавай игру в групповом чате.")
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
        await message.answer("🧹 Партия отменена. Можно создавать новую через /newgame.")
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("players"))
async def players_cmd(message: Message) -> None:
    if not group_only(message):
        return
    service = svc(message)
    game = await service.active_game(message.chat.id)
    if not game:
        await message.answer("Активной партии нет.")
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
            raise GameError("Открытого лобби нет.")
        lobby_players = await service.players(lobby["id"])

        dm_failed = []
        for p in lobby_players:
            try:
                await message.bot.send_message(
                    p["user_id"],
                    "🎟 <b>Связь с рынком проверена.</b> Игра сейчас стартует.",
                )
            except Exception:
                dm_failed.append(p["full_name"])
        if dm_failed:
            await message.answer(
                "⛔ <b>Пока не начинаю партию.</b> Не могу написать в личку: "
                + ", ".join(dm_failed)
                + ".\nИм нужно открыть бота и нажать /start, затем повторить /begin."
            )
            return

        game = await service.start_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        sheriff = await service.sheriff(game["id"])
        for p in players:
            if p["user_id"] == sheriff["user_id"]:
                text = (
                    "👮 <b>Ты первый шериф.</b>\n\n"
                    "Пока торговцы собирают мешки, можешь готовить свою самую неподкупную физиономию 😄"
                )
            else:
                text = (
                    "🎲 <b>Партия началась!</b>\n"
                    "Твоя рука уже выдана. Открой /hand и собери мешок через /bag."
                )
            await message.bot.send_message(p["user_id"], text, reply_markup=private_menu())

        await message.answer(
            f"🚪 <b>Ворота Ноттингема открыты!</b>\n"
            f"Раунд 1. Шериф: <b>{sheriff['full_name']}</b>.\n\n"
            "Все остальные собирают мешки в личке с ботом."
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
                raise GameError("Активной партии нет.")
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
            raise GameError("Сейчас ты не шериф.")
        if game["phase"] != "inspection":
            raise GameError("Ещё не все торговцы подали декларации.")
        merchants = await service.merchant_rows(game["id"])
        bribes = {}
        for m in merchants:
            offer = await service.bribe(game["id"], m["user_id"])
            bribes[m["user_id"]] = int(offer["coins"]) if offer and offer["status"] == "offered" else 0
        text = "👮 <b>Пост шерифа</b>\nВыбери торговца:"
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
            raise GameError("Сейчас ты не шериф.")
        merchant = await service.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Этот торговец уже прошёл ворота.")
        bag_size = len(loads(merchant["bag_json"]))
        good = GOODS[merchant["declared_good"]]
        offer = await service.bribe(game["id"], merchant_id)
        bribe = int(offer["coins"]) if offer and offer["status"] == "offered" else 0
        await callback.message.answer(
            f"🧳 <b>{merchant['full_name']}</b>\n"
            f"Заявлено: <b>{bag_size} × {good.emoji} {good.name}</b>\n"
            f"Предложенная взятка: <b>💰 {bribe}</b>\n\n"
            "Что делаем?",
            reply_markup=sheriff_decision_keyboard(merchant_id),
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
    new_game = await service.game(game_id)
    sheriff = await service.sheriff(game_id)
    await bot.send_message(
        new_game["chat_id"],
        f"🔄 <b>Раунд {new_game['round_no']}</b>\nНовый шериф: <b>{sheriff['full_name']}</b>.\n"
        "Остальные снова собирают мешки в личке.",
    )
    try:
        await bot.send_message(
            sheriff["user_id"],
            "👮 <b>Теперь ты шериф.</b> Когда все подадут декларации, откроется /inspect.",
            reply_markup=private_menu(),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("sheriff:pass:"))
async def sheriff_pass(callback: CallbackQuery) -> None:
    service = svc(callback)
    merchant_id = int(callback.data.rsplit(":", 1)[1])
    try:
        game = await service.game_for_user(callback.from_user.id)
        merchant = await service.player(game["id"], merchant_id)
        result = await service.pass_merchant(callback.from_user.id, merchant_id)
        await callback.message.edit_text(
            f"✅ <b>{merchant['full_name']} пропущен без проверки.</b>\n"
            f"Взятка шерифу: <b>💰 {result['bribe']}</b>."
        )
        await callback.bot.send_message(
            game["chat_id"],
            f"✅ Шериф пропустил <b>{merchant['full_name']}</b> без досмотра."
        )
        await callback.answer()
        await announce_advance(callback.bot, service, game["id"], result["advanced"])
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
        if result.truthful:
            verdict = (
                f"😇 <b>ТОРГОВЕЦ БЫЛ ЧЕСТЕН!</b>\n"
                f"Шериф выплачивает <b>💰 {outcome['merchant_delta']}</b>."
            )
        else:
            confiscated = ", ".join(GOODS[key].label for key in result.confiscated)
            verdict = (
                f"🚨 <b>ПОЙМАН!</b>\n"
                f"Конфисковано: {confiscated}\n"
                f"Штраф: <b>💰 {abs(outcome['merchant_delta'])}</b>."
            )
        text = f"🔍 <b>Мешок {merchant['full_name']}</b>\n{contents}\n\n{verdict}"
        await callback.message.edit_text(text)
        await callback.bot.send_message(game["chat_id"], text)
        await callback.answer()
        await announce_advance(callback.bot, service, game["id"], outcome["advanced"])
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)
