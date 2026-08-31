from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..db import loads
from ..keyboards import declaration_keyboard
from ..market_order import current_market_trader
from ..runtime import get_service
from ..service import GameError, GameService
from ..ui import (
    render_game_table,
    render_group_home,
    render_hand_panel,
    render_lobby_table,
    render_private_hub,
)
from ..ui_keyboards import (
    game_table_keyboard,
    group_home_keyboard,
    lobby_keyboard,
    private_hub_keyboard,
    private_start_keyboard,
)

router = Router(name="ux")


def svc(_: Message | CallbackQuery) -> GameService:
    return get_service()


async def _register(event: Message | CallbackQuery) -> None:
    await svc(event).register_user(
        event.from_user.id,
        event.from_user.username,
        event.from_user.full_name,
    )


def _is_group(event: Message | CallbackQuery) -> bool:
    message = event.message if isinstance(event, CallbackQuery) else event
    return message.chat.type in {"group", "supergroup"}


async def _private_payload(service: GameService, user_id: int) -> tuple[str, object]:
    game = await service.game_for_user(user_id)
    player = await service.player(game["id"], user_id)
    sheriff = await service.sheriff(game["id"])
    current_trader = None
    current_declarer = None
    if game["phase"] == "market" and game.get("market_start_seat") is not None:
        current_trader = await current_market_trader(service, game["id"])
    if game["phase"] == "declaration":
        current_declarer = await service.current_declarer(game["id"])

    text = render_private_hub(
        game,
        player,
        sheriff,
        current_trader=current_trader,
        current_declarer=current_declarer,
    )
    keyboard = private_hub_keyboard(
        phase=game["phase"],
        is_sheriff=sheriff["user_id"] == user_id,
        is_current_trader=bool(current_trader and current_trader["user_id"] == user_id),
        market_order_missing=game["phase"] == "market" and game.get("market_start_seat") is None,
        is_current_declarer=bool(current_declarer and current_declarer["user_id"] == user_id),
        resolved=bool(player["resolved"]),
    )
    return text, keyboard


async def _render_group_table(service: GameService, chat_id: int) -> tuple[str, object]:
    game = await service.active_game(chat_id)
    if not game:
        return render_group_home(), group_home_keyboard()
    players = await service.players(game["id"])
    if game["status"] == "lobby":
        return render_lobby_table(players, game["owner_id"]), lobby_keyboard()

    sheriff = await service.sheriff(game["id"])
    current_trader = None
    current_declarer = None
    if game["phase"] == "market" and game.get("market_start_seat") is not None:
        current_trader = await current_market_trader(service, game["id"])
    if game["phase"] == "declaration":
        current_declarer = await service.current_declarer(game["id"])
    return (
        render_game_table(
            game,
            players,
            sheriff,
            current_trader=current_trader,
            current_declarer=current_declarer,
        ),
        game_table_keyboard(),
    )


async def _edit_or_send_table(callback: CallbackQuery) -> None:
    service = svc(callback)
    text, keyboard = await _render_group_table(service, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


async def _create_lobby(message: Message) -> None:
    if not _is_group(message):
        await message.answer("Створювати партію потрібно в групі.")
        return
    await _register(message)
    service = svc(message)
    try:
        game = await service.create_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        await message.answer(
            render_lobby_table(players, game["owner_id"]),
            reply_markup=lobby_keyboard(),
        )
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


async def _join_lobby(message: Message) -> None:
    if not _is_group(message):
        return
    await _register(message)
    service = svc(message)
    try:
        game = await service.join_game(message.chat.id, message.from_user.id)
        players = await service.players(game["id"])
        await message.answer(
            render_lobby_table(players, game["owner_id"]),
            reply_markup=lobby_keyboard(),
        )
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


async def _begin_game(message: Message) -> None:
    if not _is_group(message):
        return
    await _register(message)
    service = svc(message)
    try:
        lobby = await service.active_game(message.chat.id)
        if not lobby or lobby["status"] != "lobby":
            raise GameError("Відкритого лобі немає.")
        if lobby["owner_id"] != message.from_user.id:
            raise GameError("Почати гру може лише творець партії.")
        players = await service.players(lobby["id"])
        failed: list[str] = []
        for player in players:
            try:
                await message.bot.send_message(
                    player["user_id"],
                    "🎟 <b>Перевірка зв'язку успішна.</b>",
                )
            except Exception:
                failed.append(player["full_name"])
        if failed:
            await message.answer(
                "⛔ Не можу запустити партію: ці гравці ще не відкрили бота в ЛС:\n"
                + "\n".join(f"• {name}" for name in failed)
                + "\n\nНехай натиснуть /start у приватному чаті з ботом."
            )
            return

        game = await service.start_game(message.chat.id, message.from_user.id)
        sheriff = await service.sheriff(game["id"])
        players = await service.players(game["id"])
        for player in players:
            text, keyboard = await _private_payload(service, player["user_id"])
            await message.bot.send_message(player["user_id"], text, reply_markup=keyboard)

        table_text, table_keyboard = await _render_group_table(service, message.chat.id)
        await message.answer(
            "🚪 <b>ВОРОТА НОТТІНГЕМА ВІДЧИНЕНО!</b>\n"
            f"Перший шериф: <b>{sheriff['full_name']}</b>\n\n"
            "Відтепер основні дії доступні кнопками — відкривайте «МОЯ ПАНЕЛЬ».",
        )
        await message.answer(table_text, reply_markup=table_keyboard)
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(CommandStart())
async def ux_start(message: Message) -> None:
    await _register(message)
    if _is_group(message):
        text, keyboard = await _render_group_table(svc(message), message.chat.id)
        await message.answer(text, reply_markup=keyboard)
        return

    try:
        text, keyboard = await _private_payload(svc(message), message.from_user.id)
        await message.answer(text, reply_markup=keyboard)
    except GameError:
        await message.answer(
            "🏰 <b>ШЕРИФ НОТТІНГЕМА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Приватний канал готовий. Коли приєднаєшся до партії в групі, "
            "тут з'являться твоя рука, мішок, декларації та угоди.",
            reply_markup=private_start_keyboard(),
        )


@router.message(Command("newgame"))
async def ux_newgame(message: Message) -> None:
    await _create_lobby(message)


@router.message(Command("join"))
async def ux_join(message: Message) -> None:
    await _join_lobby(message)


@router.message(Command("begin"))
async def ux_begin(message: Message) -> None:
    await _begin_game(message)


@router.callback_query(F.data == "ui:create")
async def ui_create(callback: CallbackQuery) -> None:
    if not _is_group(callback):
        await callback.answer("Створи гру в групі.", show_alert=True)
        return
    await _register(callback)
    service = svc(callback)
    try:
        game = await service.create_game(callback.message.chat.id, callback.from_user.id)
        players = await service.players(game["id"])
        await callback.message.edit_text(
            render_lobby_table(players, game["owner_id"]),
            reply_markup=lobby_keyboard(),
        )
        await callback.answer("Лобі створено")
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:join")
async def ui_join(callback: CallbackQuery) -> None:
    await _register(callback)
    try:
        await svc(callback).join_game(callback.message.chat.id, callback.from_user.id)
        await _edit_or_send_table(callback)
        await callback.answer("Ти в грі ✅")
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:leave")
async def ui_leave(callback: CallbackQuery) -> None:
    try:
        await svc(callback).leave_lobby(callback.message.chat.id, callback.from_user.id)
        await _edit_or_send_table(callback)
        await callback.answer("Ти вийшов з лобі")
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:begin")
async def ui_begin(callback: CallbackQuery) -> None:
    await _register(callback)
    service = svc(callback)
    try:
        lobby = await service.active_game(callback.message.chat.id)
        if not lobby or lobby["status"] != "lobby":
            raise GameError("Відкритого лобі немає.")
        if lobby["owner_id"] != callback.from_user.id:
            raise GameError("Почати гру може лише творець партії.")
        players = await service.players(lobby["id"])
        failed: list[str] = []
        for player in players:
            try:
                await callback.bot.send_message(player["user_id"], "🎟 <b>Зв'язок із Ноттінгемом є.</b>")
            except Exception:
                failed.append(player["full_name"])
        if failed:
            raise GameError(
                "Не можу написати в ЛС: " + ", ".join(failed) + ". Нехай вони натиснуть /start у боті."
            )

        game = await service.start_game(callback.message.chat.id, callback.from_user.id)
        for player in await service.players(game["id"]):
            text, keyboard = await _private_payload(service, player["user_id"])
            await callback.bot.send_message(player["user_id"], text, reply_markup=keyboard)
        await _edit_or_send_table(callback)
        await callback.answer("Партія почалася! 🏰")
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:table")
async def ui_table(callback: CallbackQuery) -> None:
    if not _is_group(callback):
        await callback.answer()
        return
    await _edit_or_send_table(callback)
    await callback.answer("Стіл оновлено")


@router.callback_query(F.data == "ui:me")
async def ui_me(callback: CallbackQuery) -> None:
    await _register(callback)
    try:
        text, keyboard = await _private_payload(svc(callback), callback.from_user.id)
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=keyboard)
        await callback.answer("Панель надіслана в ЛС 🎮")
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Спочатку відкрий бота в ЛС і натисни /start.", show_alert=True)


@router.callback_query(F.data == "ui:home")
async def ui_home(callback: CallbackQuery) -> None:
    try:
        text, keyboard = await _private_payload(svc(callback), callback.from_user.id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:hand")
async def ui_hand(callback: CallbackQuery) -> None:
    try:
        service = svc(callback)
        game = await service.game_for_user(callback.from_user.id)
        player = await service.player(game["id"], callback.from_user.id)
        await callback.message.answer(
            render_hand_panel(loads(player["hand_json"])),
            reply_markup=private_start_keyboard(),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:declare")
async def ui_declare(callback: CallbackQuery) -> None:
    try:
        service = svc(callback)
        game = await service.game_for_user(callback.from_user.id)
        if game["phase"] != "declaration":
            raise GameError("Зараз не етап декларування.")
        current = await service.current_declarer(game["id"])
        if not current or current["user_id"] != callback.from_user.id:
            raise GameError("Зараз не твоя черга декларувати.")
        player = await service.player(game["id"], callback.from_user.id)
        bag_size = len(loads(player["bag_json"]))
        await callback.message.answer(
            "📜 <b>ДЕКЛАРАЦІЯ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"У мішку: <b>{bag_size}</b> карт. Кількість бот уже знає.\n"
            "Обери <b>один дозволений товар</b>, який заявляєш шерифу:",
            reply_markup=declaration_keyboard(),
        )
        await callback.answer()
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)


@router.callback_query(F.data == "ui:rules")
async def ui_rules(callback: CallbackQuery) -> None:
    text = (
        "📜 <b>ШВИДКІ ПРАВИЛА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛒 <b>Торгівля:</b> скинь 0–5 карт і добери до 6.\n"
        "🎒 <b>Мішок:</b> поклади 1–5 товарів та запечатай.\n"
        "📜 <b>Декларація:</b> назви точну кількість і лише один дозволений вид товару.\n"
        "🔍 <b>Огляд:</b> шериф пропускає або відкриває мішок.\n"
        "🤝 <b>Угоди:</b> золото, товари, блеф і домовленості дозволені.\n\n"
        "🏆 Перемагає найбагатший торговець після фінального підрахунку."
    )
    await callback.answer()
    await callback.message.answer(text)
