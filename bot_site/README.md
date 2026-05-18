# Панель бота

Frontend-панель для Discord-бота из этого репозитория.

## Структура

В текущем проекте сайт лежит в папке `bot_site`:

- `bot_site/index.html`
- `bot_site/app.js`
- `bot_site/api.js`
- `bot_site/styles.css`
- `bot_site/vercel.json`
- `bot_site/package.json`

Python-бот и его backend API лежат уровнем выше: `bot.py` и `cogs/dashboard_api.py`.

## Что теперь умеет сайт

- Загружать серверы, каналы и роли через API запущенного бота.
- Выполнять whitelist JSON-действия, а не произвольные консольные строки:
  `message.embed`, `moderation.clear`, `music.play`, `reaction_roles.create`, `config.set`, `automod.add_words`.
- Настраивать систему варнов: срок спада, пороги, муты/timeouts, kick и ban.
- Если API не настроен, кнопки оставляют fallback: собирают и копируют команду для терминала бота.
- Discord OAuth2 поддерживается опционально для публичной панели. Для локального владельца проще использовать `DASHBOARD_TOKEN`.

## Локальный запуск

1. В корневом `.env` добавь минимум:

```text
DISCORD_TOKEN=токен_бота
DASHBOARD_TOKEN=длинный_секретный_токен
DASHBOARD_API_HOST=127.0.0.1
DASHBOARD_API_PORT=8080
DASHBOARD_PUBLIC_URL=http://localhost:8080
DASHBOARD_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:4173,http://127.0.0.1:4173
```

2. Запусти бота из корня проекта:

```powershell
python bot.py
```

3. Открой сайт, который теперь отдаёт сам backend:

```text
http://localhost:8080
```

4. Если нужен отдельный статический режим, запусти сайт:

```powershell
cd bot_site
python -m http.server 4173
```

Открой `http://localhost:4173`, зайди в `Настройки сервера`, укажи:

```text
URL API бота: http://localhost:8080
Токен панели: значение DASHBOARD_TOKEN
```

После этого нажми `Проверить API` и `Загрузить серверы`.

Если `DASHBOARD_TOKEN` и Discord OAuth не настроены, локальный доступ без авторизации включается только для `127.0.0.1` / `localhost`.

Для варнов и мутов проверь, что у бота на сервере есть права `Moderate Members`, `Kick Members` или `Ban Members` в зависимости от выбранных порогов.

## Discord OAuth2

Для публичной панели добавь в Discord Developer Portal redirect URL:

```text
http://localhost:8080/api/auth/callback
```

И задай в `.env`:

```text
DISCORD_CLIENT_ID=client_id_приложения
DISCORD_CLIENT_SECRET=client_secret_приложения
DASHBOARD_DISCORD_REDIRECT_URI=http://localhost:8080/api/auth/callback
```

Пользователь увидит только серверы, где есть бот и где у пользователя есть права владельца, администратора, Manage Server или Manage Roles.

## Деплой на Vercel

Для этого репозитория укажи:

```text
Root Directory: bot_site
Framework Preset: Other
Build Command: npm run build
Output Directory: .
```

Важно: Vercel деплоит только статический frontend. Python-бот и `cogs/dashboard_api.py` должны быть запущены отдельно на сервере/ПК с доступным `DASHBOARD_PUBLIC_URL`. Если frontend открыт по HTTPS, API тоже лучше отдавать по HTTPS.

## Проверки

```powershell
cd bot_site
npm run lint
npm test
```
