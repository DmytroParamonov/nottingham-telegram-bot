# 🏰 Nottingham Telegram Bot

Фанатская Telegram-игра про рынок, декларации, контрабанду, взятки и шерифа. Проект не использует официальный арт или текст правил и не является официальным продуктом правообладателей настольной игры.

## Что уже работает

- 3–8 игроков в групповом чате;
- личные руки игроков в DM;
- мешок на 1–5 товаров;
- декларация количества и одного легального типа товара;
- легальные товары и контрабанда;
- денежные взятки шерифу;
- шериф может пропустить или вскрыть мешок;
- автоматические штрафы и компенсации;
- конфискация неправильно задекларированных товаров;
- смена шерифа по кругу;
- две смены шерифа на каждого игрока;
- финальный подсчёт: золото + стоимость товаров + бонусы большинства;
- SQLite, поэтому отдельный сервер БД не нужен.

## Стек

- Python 3.11+
- aiogram 3
- SQLite / aiosqlite

## Быстрый запуск

```bash
git clone <YOUR_REPOSITORY_URL>
cd nottingham-telegram-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

В `.env`:

```env
BOT_TOKEN=токен_от_BotFather
DATABASE_PATH=data/nottingham.sqlite3
```

## Как играть

1. Каждый игрок открывает бота в личке и нажимает `/start`.
2. Добавьте бота в общий Telegram-чат.
3. Создатель пишет `/newgame`.
4. Остальные пишут `/join`.
5. Создатель запускает игру `/begin`.
6. Все торговцы получают карты в личке, смотрят `/hand` и собирают `/bag`.
7. После запечатывания выбирают, какой легальный товар объявить.
8. Можно предложить денежную взятку: `/bribe 5`.
9. Когда все готовы, шериф открывает `/inspect` и принимает решения.
10. После последнего раунда бот автоматически покажет победителя.

## Команды

### В группе

- `/newgame` — создать лобби
- `/join` — войти
- `/leave` — выйти из лобби
- `/players` — список игроков
- `/begin` — начать
- `/status` — статус
- `/cancelgame` — отменить активную партию

### В личке

- `/start` — меню
- `/hand` — рука
- `/bag` — мешок
- `/bribe 5` — предложить 5 монет
- `/inspect` — панель текущего шерифа
- `/status` — статус партии

## Raspberry Pi / systemd

Пример `/etc/systemd/system/nottingham-bot.service`:

```ini
[Unit]
Description=Nottingham Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nottingham-telegram-bot
ExecStart=/home/pi/nottingham-telegram-bot/.venv/bin/python /home/pi/nottingham-telegram-bot/main.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nottingham-bot
sudo systemctl status nottingham-bot
```

Если пользователь Raspberry Pi у тебя называется иначе, замени `User=pi` и пути.

## Что логично добавить во второй версии

- взятки товарами и будущими обещаниями;
- специальные королевские товары;
- расширенную статистику профиля;
- достижения и титулы;
- красивые карточки товаров;
- режимы партии и настройку числа кругов;
- админ-команду восстановления партии после спорной ситуации.
