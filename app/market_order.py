from __future__ import annotations

from .service import GameError, GameService


async def market_order(service: GameService, game_id: int) -> list[dict]:
    """Return merchants clockwise from the sheriff-selected first trader."""
    game = await service.game(game_id)
    players = await service.players(game_id)
    sheriff = await service.sheriff(game_id)
    start = game.get("market_start_seat")
    if start is None:
        return []

    by_seat = {int(player["seat"]): player for player in players}
    order: list[dict] = []
    for step in range(len(players)):
        seat = (int(start) + step) % len(players)
        player = by_seat[seat]
        if player["user_id"] != sheriff["user_id"]:
            order.append(player)
    return order


async def current_market_trader(service: GameService, game_id: int) -> dict | None:
    for merchant in await market_order(service, game_id):
        refreshed = await service.player(game_id, merchant["user_id"])
        if not refreshed["resolved"]:
            return refreshed
    return None


async def choose_first_trader(
    service: GameService,
    sheriff_id: int,
    merchant_id: int,
) -> dict:
    game = await service.game_for_user(sheriff_id)
    if game["phase"] != "market":
        raise GameError("Зараз не етап «Торгівля».")
    sheriff = await service.sheriff(game["id"])
    if sheriff["user_id"] != sheriff_id:
        raise GameError("Першого торговця обирає лише поточний шериф.")
    if game.get("market_start_seat") is not None:
        raise GameError("Порядок торгівлі цього раунду вже визначено.")

    merchant = await service.player(game["id"], merchant_id)
    if merchant["user_id"] == sheriff_id:
        raise GameError("Шериф не бере участі в Торгівлі.")

    await service.db.execute(
        "UPDATE games SET market_start_seat=? WHERE id=?",
        (merchant["seat"], game["id"]),
    )
    return merchant


async def ensure_market_turn(service: GameService, user_id: int) -> dict:
    game = await service.game_for_user(user_id)
    if game["phase"] != "market":
        raise GameError("Зараз не етап «Торгівля».")
    if game.get("market_start_seat") is None:
        raise GameError("Шериф ще не обрав першого торговця.")
    current = await current_market_trader(service, game["id"])
    if current is None:
        raise GameError("Торгівлю вже завершено.")
    if current["user_id"] != user_id:
        raise GameError(f"Зараз торгує {current['full_name']}. Дочекайся своєї черги.")
    return current


async def reset_market_order(service: GameService, game_id: int) -> None:
    await service.db.execute(
        "UPDATE games SET market_start_seat=NULL WHERE id=?",
        (game_id,),
    )
