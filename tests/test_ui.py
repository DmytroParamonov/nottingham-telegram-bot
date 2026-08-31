from app.ui import render_game_table, render_lobby_table, render_private_hub
from app.ui_keyboards import game_table_keyboard, lobby_keyboard, private_hub_keyboard


def test_lobby_escapes_player_names_and_has_button_flow():
    players = [
        {
            "user_id": 1,
            "full_name": "<b>Шахрай</b>",
        }
    ]
    text = render_lobby_table(players, owner_id=1)
    assert "&lt;b&gt;Шахрай&lt;/b&gt;" in text
    assert "<b>Шахрай</b>" not in text

    callbacks = [button.callback_data for row in lobby_keyboard().inline_keyboard for button in row]
    assert "ui:join" in callbacks
    assert "ui:begin" in callbacks
    assert "ui:table" in callbacks


def test_private_hub_shows_only_phase_relevant_primary_action():
    game = {
        "round_no": 2,
        "phase": "declaration",
        "market_start_seat": 1,
    }
    player = {
        "user_id": 10,
        "full_name": "Олена",
        "coins": 44,
        "hand_json": '["apple","cheese"]',
        "market_json": '["apple"]',
        "bag_json": '["pepper","apple"]',
        "bag_locked": 1,
        "declared_good": None,
        "resolved": 0,
    }
    sheriff = {"user_id": 20, "full_name": "Тарас"}
    text = render_private_hub(
        game,
        player,
        sheriff,
        current_declarer=player,
    )
    assert "Твоя черга декларувати" in text

    kb = private_hub_keyboard(
        phase="declaration",
        is_sheriff=False,
        is_current_declarer=True,
    )
    callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
    assert "ui:declare" in callbacks
    assert "menu:bag" not in callbacks
    assert "sheriff:list" not in callbacks


def test_group_game_table_hides_contraband_identity():
    game = {"round_no": 1, "phase": "inspection"}
    sheriff = {"user_id": 1, "full_name": "Марко"}
    players = [
        {
            "user_id": 1,
            "full_name": "Марко",
            "coins": 50,
            "market_json": '[]',
            "resolved": 0,
            "bag_locked": 0,
            "declared_good": None,
        },
        {
            "user_id": 2,
            "full_name": "Катерина",
            "coins": 42,
            "market_json": '["apple","pepper","silk"]',
            "resolved": 0,
            "bag_locked": 1,
            "declared_good": "apple",
        },
    ]
    text = render_game_table(game, players, sheriff)
    assert "контрабанда ×2" in text
    assert "Перець" not in text
    assert "Шовк" not in text

    callbacks = [button.callback_data for row in game_table_keyboard().inline_keyboard for button in row]
    assert "ui:me" in callbacks
    assert "ui:table" in callbacks
