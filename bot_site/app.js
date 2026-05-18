const storageKey = "botPanelState:v1";

const state = {
  route: "overview",
  moduleFilter: "all",
  commandFilter: "all",
  commandSearch: "",
  settings: loadSettings(),
  api: {
    status: "idle",
    message: "",
    guilds: [],
    textChannels: [],
    voiceChannels: [],
    roles: [],
    guildSettings: {},
    warnPolicy: defaultWarnPolicy(),
    modlog: null,
    auth: null,
    me: null,
    lastResult: ""
  },
  reactionRows: [
    { emoji: "🎮", role: "GTA V" },
    { emoji: "⛏️", role: "Minecraft" },
    { emoji: "🔫", role: "CS 2" }
  ]
};

const modules = [
  {
    id: "utility",
    icon: "⚙️",
    title: "Утилиты",
    category: "Настройки модулей",
    description: "Общие возможности, справка, информация о сервере и быстрые действия.",
    status: "ready",
    commands: ["/help", "/server", "/invites"]
  },
  {
    id: "server-settings",
    icon: "🛠",
    title: "Настройки сервера",
    category: "Основное",
    description: "ID сервера, каналы по умолчанию, права доступа и локальные настройки панели.",
    status: "ready",
    commands: ["/config view", "/config set", "/config delete"]
  },
  {
    id: "embed-messages",
    icon: "🧩",
    title: "Embed-сообщения",
    category: "Основное",
    description: "Конструктор embed-сообщений для публикации через консоль бота.",
    status: "ready",
    commands: ["embed"]
  },
  {
    id: "moderation",
    icon: "🛡",
    title: "Модерация",
    category: "Модерация",
    description: "Очистка сообщений, warn, kick, ban, unban и журнал модерации.",
    status: "ready",
    commands: ["/clear", "/warn", "/warnings", "/clearwarns", "/unwarn", "/kick", "/ban", "/mban", "/randban", "/unban", "/modlog"]
  },
  {
    id: "automod",
    icon: "🤖",
    title: "Автомодерация",
    category: "Модерация",
    description: "Антимат, AI-модерация, анти-рейд и базовая защита сервера.",
    status: "ready",
    commands: ["/addword", "/addworl", "/delword", "/delworl", "/words", "/config set antimat_enabled"]
  },
  {
    id: "music",
    icon: "🎵",
    title: "Музыка",
    category: "Развлечения",
    description: "Музыкальное меню, очередь, перемотка, скорость и субтитры.",
    status: "ready",
    commands: ["/play", "/menu", "/shuffle", "/skip", "/stop", "/queue", "/jump", "/seek", "/speed", "/lyrics", "/now"]
  },
  {
    id: "reaction-roles",
    icon: "🎭",
    title: "Роли по реакциям",
    category: "Роли",
    description: "Роли по реакциям в стиле Carl-bot и ProBot self roles.",
    status: "ready",
    commands: ["/reactionroles create", "/reactionroles add", "/reactionroles remove", "/reactionroles list"]
  },
  {
    id: "auto-roles",
    icon: "🏷",
    title: "Авто-роли",
    category: "Роли",
    description: "Макет будущего модуля автоматической выдачи ролей новым участникам.",
    status: "planned",
    commands: []
  },
  {
    id: "welcome",
    icon: "👋",
    title: "Приветствия и прощания",
    category: "Участники",
    description: "Макет приветствий и прощаний: канал, текст, embed и переменные участника.",
    status: "planned",
    commands: []
  },
  {
    id: "auto-responder",
    icon: "✈️",
    title: "Автоответчик",
    category: "Участники",
    description: "Макет автоответов: триггер, ответ, режим exact/contains и задержка.",
    status: "planned",
    commands: []
  },
  {
    id: "leveling",
    icon: "⇅",
    title: "Система уровней",
    category: "Активность",
    description: "Макет XP, уровней, наград ролями и таблицы лидеров.",
    status: "planned",
    premium: true,
    commands: []
  },
  {
    id: "logs",
    icon: "↩",
    title: "Логи",
    category: "Модерация",
    description: "Журнал действий модерации уже хранится ботом; здесь собран интерфейс просмотра.",
    status: "ready",
    commands: ["/modlog"]
  },
  {
    id: "colors",
    icon: "🎨",
    title: "Цвета",
    category: "Роли",
    description: "Макет управления цветовыми ролями и палитрами.",
    status: "planned",
    commands: []
  },
  {
    id: "starboard",
    icon: "⭐",
    title: "Звёздная доска",
    category: "Сообщество",
    description: "Макет выделения сообщений по реакциям.",
    status: "planned",
    commands: []
  },
  {
    id: "temporary-channels",
    icon: "⊞",
    title: "Временные каналы",
    category: "Голос",
    description: "Макет временных голосовых каналов.",
    status: "planned",
    commands: []
  },
  {
    id: "tickets",
    icon: "🎫",
    title: "Тикеты",
    category: "Поддержка",
    description: "Макет тикетов для поддержки и приватных обращений.",
    status: "planned",
    premium: true,
    commands: []
  },
  {
    id: "notifications",
    icon: "📣",
    title: "Уведомления",
    category: "Уведомления",
    description: "Макет Twitch, YouTube, Kick и Reddit уведомлений.",
    status: "planned",
    premium: true,
    commands: []
  },
  {
    id: "developer",
    icon: "🖥",
    title: "Панель разработчика",
    category: "Система",
    description: "Dev-команды, список серверов, инвайты, botinfo и shutdown.",
    status: "ready",
    commands: ["/dev", "/server", "/invites"]
  }
];

const enabledModules = modules.filter((item) => item.status === "ready");

const commands = [
  cmd("Общее", "/help", "Показать список команд бота.", "/help", "help"),
  cmd("Общее", "/server", "Показать список серверов, где есть бот. Только владелец.", "/server", "servers"),
  cmd("Общее", "/invites", "Получить инвайты на сервера, где есть бот. Только владелец.", "/invites", "invites"),
  cmd("Модерация", "/clear", "Удалить последние сообщения в канале.", "/clear amount:10 channel:#general", "clear <channel_id> <amount>"),
  cmd("Модерация", "/kick", "Кикнуть участника с сервера.", "/kick member:@user reason:Причина", "kick <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/ban", "Забанить участника.", "/ban member:@user reason:Причина delete_messages:0", "ban <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/mban", "Забанить сразу до двух участников.", "/mban member1:@user member2:@user reason:Причина", "ban <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/randban", "Рандомно забанить до 10 участников.", "/randban count:3 reason:Причина", "ban <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/unban", "Разбанить пользователя.", "/unban user:123456789 reason:Причина", "unban <guild_id> <user_id> [reason]"),
  cmd("Модерация", "/modlog", "Показать журнал модерации сервера или участника.", "/modlog user:@user", "нет консольной команды"),
  cmd("Модерация", "/warn", "Выдать варн с авто-наказанием по настройкам сервера.", "/warn member:@user reason:Причина", "warn <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/warnings", "Показать активные варны участника.", "/warnings member:@user", "warnings <guild_id> <member_id>"),
  cmd("Модерация", "/clearwarns", "Снять активные варны участника.", "/clearwarns member:@user reason:Причина", "clearwarns <guild_id> <member_id> [reason]"),
  cmd("Модерация", "/unwarn", "Алиас для снятия активных варнов.", "/unwarn member:@user reason:Причина", "unwarn <guild_id> <member_id> [reason]"),
  cmd("Антимат", "/addword", "Добавить слово или несколько слов в бан-лист.", "/addword word:слово, слово", "addword <word, word>"),
  cmd("Антимат", "/addworl", "Алиас /addword для добавления нескольких слов через запятую.", "/addworl word:слово, слово", "addword <word, word>"),
  cmd("Антимат", "/delword", "Удалить слово или несколько слов из бан-листа.", "/delword word:слово, слово", "delword <word, word>"),
  cmd("Антимат", "/delworl", "Алиас /delword для удаления нескольких слов через запятую.", "/delworl word:слово, слово", "delword <word, word>"),
  cmd("Антимат", "/words", "Показать список запрещённых слов.", "/words", "words"),
  cmd("Музыка", "/join", "Подключить бота к голосовому каналу.", "/join", "join <voice_channel_id>"),
  cmd("Музыка", "/leave", "Отключить бота от голосового канала.", "/leave", "leave <guild_id>"),
  cmd("Музыка", "/play", "Проиграть трек, поиск или плейлист.", "/play query:название или ссылка", "play <voice_channel_id> <query>"),
  cmd("Музыка", "/menu", "Открыть музыкальное меню с кнопками.", "/menu", "menu <text_channel_id>"),
  cmd("Музыка", "/skip", "Пропустить текущий трек.", "/skip", "skip <guild_id>"),
  cmd("Музыка", "/shuffle", "Перемешать загруженную очередь/плейлист.", "/shuffle или кнопка 🔀 в /menu", "shuffle <guild_id>"),
  cmd("Музыка", "/stop", "Остановить музыку и очистить очередь.", "/stop", "stop <guild_id>"),
  cmd("Музыка", "/queue", "Показать список песен в очереди.", "/queue start:1", "queue <guild_id>"),
  cmd("Музыка", "/jump", "Переключиться на песню по номеру из списка.", "/jump position:2", "jump <guild_id> <position>"),
  cmd("Музыка", "/seek", "Перемотать текущую песню на указанную секунду.", "/seek seconds:90", "пока только slash-команда"),
  cmd("Музыка", "/speed", "Изменить скорость воспроизведения.", "/speed value:1.25", "пока только slash-команда"),
  cmd("Музыка", "/lyrics", "Включить или выключить субтитры.", "/lyrics enabled:true", "lyrics <guild_id> <channel_id|off>"),
  cmd("Музыка", "/now", "Показать текущий трек.", "/now", "now <guild_id>"),
  cmd("Роли по реакциям", "/reactionroles create", "Создать сообщение с ролями по реакциям.", "/reactionroles create channel:#roles title:Игры description:Выбери игру mappings:🎮=@GTA V; ⛏️=@Minecraft", "rr create <channel_id> | <title> | <description> | <emoji>=<role_id>"),
  cmd("Роли по реакциям", "/reactionroles add", "Добавить emoji -> роль к сообщению.", "/reactionroles add channel:#roles message_id:123 emoji:🎮 role:@GTA V", "rr add <channel_id> <message_id> <emoji> <role_id_or_name>"),
  cmd("Роли по реакциям", "/reactionroles remove", "Удалить emoji -> роль.", "/reactionroles remove channel:#roles message_id:123 emoji:🎮", "rr remove <guild_id> <message_id> <emoji>"),
  cmd("Роли по реакциям", "/reactionroles list", "Показать настроенные reaction-role сообщения.", "/reactionroles list", "rr list <guild_id>"),
  cmd("Настройки", "/config view", "Показать настройки сервера.", "/config view", "config view <guild_id>"),
  cmd("Настройки", "/config set", "Установить настройку сервера.", "/config set key:antimat_enabled value:true", "config set <guild_id> <key> <value>"),
  cmd("Настройки", "/config delete", "Удалить настройку сервера.", "/config delete key:antimat_enabled", "config delete <guild_id> <key>"),
  cmd("Разработчик", "/dev", "Панель разработчика: panel, servers, invites, shutdown, botinfo.", "/dev action:panel", "shutdown / servers / channels <guild_id>")
];

const navGroups = [
  {
    title: "Основное",
    items: [
      ["overview", "◉", "Обзор"],
      ["settings", "⚙️", "Настройки сервера"],
      ["embeds", "▣", "Embed-сообщения"],
      ["commands", "⌘", "Команды"],
      ["console", "▸", "Консоль"]
    ]
  },
  {
    title: "Настройки модулей",
    items: enabledModules
      .filter((item) => ["utility", "reaction-roles"].includes(item.id))
      .map((item) => [`module:${item.id}`, item.icon, item.title, item.status])
  },
  {
    title: "Модерация",
    items: [
      ["module:moderation", "🛡", "Модерация", "ready"],
      ["module:logs", "↩", "Логи", "ready"],
      ["module:automod", "🤖", "Автомодерация", "ready"]
    ]
  },
  {
    title: "Музыка и система",
    items: [
      ["module:music", "🎵", "Музыка", "ready"],
      ["module:developer", "🖥", "Панель разработчика", "ready"]
    ]
  }
];

document.addEventListener("DOMContentLoaded", () => {
  renderNav();
  bindGlobalActions();
  routeFromHash();
  window.addEventListener("hashchange", routeFromHash);
  autoConnectApi();
});

function cmd(category, name, description, usage, consoleCommand) {
  return { category, name, description, usage, consoleCommand };
}

function defaultWarnPolicy() {
  return {
    decayDays: 30,
    tiers: [
      { warns: 1, action: "none", durationMinutes: 0, label: "Предупреждение" },
      { warns: 2, action: "timeout", durationMinutes: 10, label: "Мут 10 минут" },
      { warns: 3, action: "timeout", durationMinutes: 60, label: "Мут 1 час" }
    ]
  };
}

function defaultApiUrl() {
  const localHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (localHosts.has(location.hostname) && location.port && location.port !== "4173") {
    return location.origin;
  }
  return "";
}

function defaultSettings() {
  return {
    guildName: "Мой сервер",
    guildId: "",
    textChannelId: "",
    voiceChannelId: "",
    rolesChannelId: "",
    apiUrl: defaultApiUrl(),
    dashboardToken: ""
  };
}

function loadSettings() {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return { ...defaultSettings(), ...stored, apiUrl: stored.apiUrl || defaultApiUrl() };
  } catch {
    return defaultSettings();
  }
}

async function autoConnectApi() {
  if (!window.BotDashboardApi?.isConfigured(state.settings) || state.api.guilds.length) {
    return;
  }
  await loadApiGuilds({ keepRoute: true, silent: true });
}

function saveSettings() {
  localStorage.setItem(storageKey, JSON.stringify(state.settings));
  updateSelectedGuild();
}

function routeFromHash() {
  const route = location.hash.replace(/^#\/?/, "") || "overview";
  state.route = route;
  document.body.classList.remove("nav-open");
  render();
}

function setRoute(route) {
  location.hash = route;
}

function render() {
  updateSelectedGuild();
  updateActiveNav();
  renderServerRail();

  if (state.route.startsWith("module:")) {
    const moduleId = state.route.split(":")[1];
    renderModule(moduleId);
    return;
  }

  const routes = {
    overview: renderOverview,
    settings: renderSettings,
    embeds: renderEmbeds,
    commands: renderCommands,
    console: renderConsole
  };

  (routes[state.route] || renderOverview)();
}

function renderNav() {
  const nav = document.querySelector("#sideNav");
  nav.innerHTML = navGroups.map((group) => `
    <div class="nav-section">${escapeHTML(group.title)}</div>
    ${group.items.map(([route, icon, label, status]) => `
      <button class="nav-button" data-route="${escapeHTML(route)}">
        <span class="nav-icon">${icon}</span>
        <span class="nav-label">${escapeHTML(label)}</span>
        ${status ? `<span class="nav-state ${status === "ready" ? "" : "dim"}"></span>` : ""}
      </button>
    `).join("")}
  `).join("")}`;
}

function renderServerRail() {
  const rail = document.querySelector("#serverRail");
  if (!rail) return;
  const guildButtons = state.api.guilds.slice(0, 8).map((guild) => {
    const initials = guild.name
      .split(/\s+/)
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    return `<button class="server-dot text-dot ${guild.id === state.settings.guildId ? "active" : ""}" title="${escapeAttr(guild.name)}" data-api-guild="${escapeAttr(guild.id)}">${escapeHTML(initials || "?")}</button>`;
  }).join("");

  rail.innerHTML = `
    <button class="server-dot ${state.route === "overview" ? "active" : ""}" title="Главная" data-route="overview">
      <img src="./assets/bot-mark.svg" alt="">
    </button>
    ${guildButtons}
    <button class="server-dot add-dot" title="Загрузить серверы" data-route="settings">+</button>
  `;
}

function bindGlobalActions() {
  document.body.addEventListener("click", (event) => {
    const guildButton = event.target.closest("[data-api-guild]");
    if (guildButton) {
      setRoute("settings");
      selectApiGuild(guildButton.dataset.apiGuild);
      return;
    }

    const routeButton = event.target.closest("[data-route]");
    if (routeButton) {
      setRoute(routeButton.dataset.route);
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      copyText(copyButton.dataset.copy);
      return;
    }

  });

  const searchFocus = document.querySelector("#searchFocus");
  searchFocus.addEventListener("click", () => {
    setRoute("commands");
    setTimeout(() => document.querySelector("#commandSearch")?.focus(), 40);
  });
}

function updateSelectedGuild() {
  document.querySelector("#selectedGuildName").textContent = state.settings.guildName || "Мой сервер";
  document.querySelector("#selectedGuildId").textContent = state.settings.guildId ? `ID: ${state.settings.guildId}` : "ID сервера не задан";
}

function updateActiveNav() {
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.route === state.route);
  });
}

function setHeader(eyebrow, title) {
  document.querySelector("#pageEyebrow").textContent = eyebrow;
  document.querySelector("#pageTitle").textContent = title;
}

function renderOverview() {
  setHeader("Панель", "Обзор модулей");
  const content = document.querySelector("#content");
  const categories = ["all", ...new Set(enabledModules.map((item) => item.category))];
  const visible = state.moduleFilter === "all" ? enabledModules : enabledModules.filter((item) => item.category === state.moduleFilter);

  content.innerHTML = `
    <div class="stats-grid">
      <div class="stat"><span>Серверов у бота</span><strong>${state.api.guilds.length || "—"}</strong></div>
      <div class="stat"><span>Команд в каталоге</span><strong>${commands.length}</strong></div>
      <div class="stat"><span>Рабочих модулей</span><strong>${enabledModules.length}</strong></div>
      <div class="stat"><span>API</span><strong>${window.BotDashboardApi?.isConfigured(state.settings) ? "ON" : "OFF"}</strong></div>
    </div>

    ${renderGuildOverview()}

    <div class="toolbar">
      <div class="segmented">
        ${categories.map((category) => `<button class="chip ${state.moduleFilter === category ? "active" : ""}" data-filter-module="${escapeHTML(category)}">${category === "all" ? "Все" : escapeHTML(category)}</button>`).join("")}
      </div>
      <button class="secondary-button" data-route="commands">Открыть команды</button>
    </div>

    <div class="module-grid">
      ${visible.map(renderModuleCard).join("")}
    </div>
  `;

  content.querySelectorAll("[data-filter-module]").forEach((button) => {
    button.addEventListener("click", () => {
      state.moduleFilter = button.dataset.filterModule;
      renderOverview();
    });
  });
  content.querySelector("#overviewLoadGuilds")?.addEventListener("click", () => loadApiGuilds({ keepRoute: true }));
}

function renderGuildOverview() {
  if (!window.BotDashboardApi?.isConfigured(state.settings)) {
    return `
      <div class="note-box section">
        <h2>Серверы бота</h2>
        <p class="muted">Укажи URL API и токен панели в настройках, затем загрузи серверы. После этого здесь появятся реальные Discord-серверы, где находится бот.</p>
        <div class="action-row">
          <button class="primary-button" data-route="settings">Подключить API</button>
        </div>
      </div>
    `;
  }

  if (!state.api.guilds.length) {
    return `
      <div class="note-box section">
        <h2>Серверы бота</h2>
        <p class="muted">API настроен. Нажми кнопку, чтобы получить список серверов у запущенного бота.</p>
        <div class="action-row">
          <button class="primary-button" id="overviewLoadGuilds">Загрузить серверы</button>
        </div>
      </div>
    `;
  }

  return `
    <div class="section">
      <h2>Серверы бота</h2>
      <div class="guild-grid">
        ${state.api.guilds.map((guild) => `
          <button class="guild-card ${guild.id === state.settings.guildId ? "active" : ""}" data-api-guild="${escapeAttr(guild.id)}">
            <strong>${escapeHTML(guild.name)}</strong>
            <span>ID: ${escapeHTML(guild.id)}</span>
            <small>${guild.memberCount ?? "—"} участников</small>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderModuleCard(item) {
  return `
    <article class="module-card">
      <div class="module-card-header">
        <div class="module-icon">${item.icon}</div>
        <div class="module-title">
          <strong>${escapeHTML(item.title)}</strong>
          <span>${escapeHTML(item.category)}</span>
        </div>
        <div class="module-actions">
          <span class="badge green">Работает</span>
        </div>
      </div>
      <p>${escapeHTML(item.description)}</p>
      <div class="module-card-footer">
        <button class="secondary-button" data-route="module:${escapeHTML(item.id)}">Открыть</button>
      </div>
    </article>
  `;
}

function renderModule(moduleId) {
  const item = enabledModules.find((module) => module.id === moduleId) || enabledModules[0];
  setHeader(item.category, item.title);

  const content = document.querySelector("#content");
  const custom = {
    "server-settings": renderSettingsInner,
    "embed-messages": renderEmbedsInner,
    "moderation": renderModerationInner,
    "automod": renderAutomodInner,
    "music": renderMusicInner,
    "reaction-roles": renderReactionRolesInner,
    "logs": renderLogsInner,
    "developer": renderDeveloperInner
  };

  content.innerHTML = `
    <div class="workspace">
      <div>
        <div class="section">
          <div class="note-box">
            <div class="module-card-header">
              <div class="module-icon">${item.icon}</div>
              <div class="module-title">
                <strong>${escapeHTML(item.title)}</strong>
                <span>${escapeHTML(item.description)}</span>
              </div>
              <span class="badge ${item.status === "ready" ? "green" : "amber"}">${item.status === "ready" ? "Готово" : "Макет"}</span>
            </div>
          </div>
        </div>
        <div id="moduleMain">${custom[item.id] ? custom[item.id]() : renderPlannedModuleInner(item)}</div>
      </div>
      <aside>
        ${renderModuleCommands(item)}
        ${renderConnectionNote()}
      </aside>
    </div>
  `;

  bindDynamicForms();
}

function renderModuleCommands(item) {
  const list = item.commands.length
    ? item.commands.map((name) => `<div class="setting-row"><div><strong><code>${escapeHTML(name)}</code></strong><span>${commandDescription(name)}</span></div><button class="ghost-button" data-copy="${escapeAttr(name)}">Копировать</button></div>`).join("")
    : `<div class="empty-state">Команды для этого модуля пока не подключены к боту.</div>`;

  return `
    <div class="section">
      <h2>Команды модуля</h2>
      <div class="setting-list">${list}</div>
    </div>
  `;
}

function renderConnectionNote() {
  return `
    <div class="note-box">
      <h3>Подключение к боту</h3>
      <p class="muted">Если <code>URL API бота</code> задан и бот запущен, кнопки выполняют действия через защищенный JSON API. Без API сайт оставляет fallback: собирает и копирует команду для терминала.</p>
      <div class="action-row">
        <button class="secondary-button" data-route="settings">Настроить API</button>
        <button class="ghost-button" data-route="console">Команды консоли</button>
      </div>
    </div>
  `;
}

function renderPlannedModuleInner(item) {
  const settings = [
    ["Включить модуль", "Переключатель для будущего backend-подключения."],
    ["Канал по умолчанию", "ID канала, где модуль будет работать."],
    ["Исключённые роли", "Роли, которые модуль должен игнорировать."],
    ["Логи", "Канал для событий этого модуля."]
  ];

  return `
    <div class="section">
      <h2>Настройки</h2>
      <div class="setting-list">
        ${settings.map(([title, text]) => `
          <div class="setting-row">
            <div><strong>${title}</strong><span>${text}</span></div>
            <button class="toggle"></button>
          </div>
        `).join("")}
      </div>
    </div>
    <div class="note-box">
      <h3>${escapeHTML(item.title)} готов как интерфейс</h3>
      <p class="muted">Этот блок сделан как ProBot-style страница. В текущем Python-боте для него ещё нужно добавить отдельный cog/backend-логику.</p>
    </div>
  `;
}

function renderSettings() {
  setHeader("Основное", "Настройки сервера");
  document.querySelector("#content").innerHTML = renderSettingsInner();
  bindDynamicForms();
}

function renderApiStatus() {
  if (!state.api.message && !state.api.lastResult) {
    return "";
  }
  const statusClass = state.api.status === "error" ? "danger" : state.api.status === "ok" ? "green" : "amber";
  return `
    <div class="api-status ${statusClass}">
      ${state.api.message ? `<strong>${escapeHTML(state.api.message)}</strong>` : ""}
      ${state.api.lastResult ? `<pre class="code-output">${escapeHTML(state.api.lastResult)}</pre>` : ""}
    </div>
  `;
}

function renderAuthStatus() {
  const auth = state.api.auth || {};
  const user = state.api.me?.user;
  const mode = state.api.me?.mode || (auth.unsafeNoAuth ? "unsafe" : auth.token ? "token" : auth.discordOAuth ? "oauth" : "none");
  const label = user
    ? `${user.username || user.global_name || user.id} (${mode})`
    : mode === "token"
      ? "Токен панели активен"
      : mode === "unsafe"
        ? "Локальный вход без токена"
        : auth.discordOAuth
          ? "Можно войти через Discord"
          : "OAuth не настроен";

  return `
    <div class="api-status ${user || mode === "token" || mode === "unsafe" ? "green" : "amber"}">
      <strong>Вход</strong>
      <p>${escapeHTML(label)}</p>
      <div class="action-row">
        <button class="secondary-button" id="discordLogin">Войти через Discord</button>
        <button class="ghost-button" id="discordLogout">Выйти</button>
      </div>
    </div>
  `;
}

function renderSettingsInner() {
  const guildOptions = state.api.guilds
    .map((guild) => `<option value="${escapeAttr(guild.id)}" ${guild.id === state.settings.guildId ? "selected" : ""}>${escapeHTML(guild.name)} (${escapeHTML(guild.id)})</option>`)
    .join("");
  const textOptions = state.api.textChannels
    .map((channel) => `<option value="${escapeAttr(channel.id)}" ${channel.id === state.settings.textChannelId ? "selected" : ""}>#${escapeHTML(channel.name)} (${escapeHTML(channel.id)})</option>`)
    .join("");
  const voiceOptions = state.api.voiceChannels
    .map((channel) => `<option value="${escapeAttr(channel.id)}" ${channel.id === state.settings.voiceChannelId ? "selected" : ""}>${escapeHTML(channel.name)} (${escapeHTML(channel.id)})</option>`)
    .join("");
  const roleOptions = state.api.roles
    .map((role) => `<option value="${escapeAttr(role.id)}">${escapeHTML(role.name)} (${escapeHTML(role.id)})</option>`)
    .join("");

  return `
    <div class="workspace">
      <div class="form-box">
        <h2>Подключение и ID</h2>
        <div class="form-grid">
          ${field("guildName", "Название сервера", state.settings.guildName, "Мой сервер")}
          ${field("guildId", "ID сервера", state.settings.guildId, "100000000000000000")}
          ${field("textChannelId", "ID текстового канала", state.settings.textChannelId, "100000000000000001")}
          ${field("voiceChannelId", "ID голосового канала", state.settings.voiceChannelId, "100000000000000002")}
          ${field("rolesChannelId", "ID канала ролей", state.settings.rolesChannelId, "100000000000000003")}
          ${field("apiUrl", "URL API бота", state.settings.apiUrl, "http://localhost:8080")}
          ${field("dashboardToken", "Токен панели", state.settings.dashboardToken, "секретный токен", "password")}
        </div>
        <div class="action-row">
          <button class="primary-button" id="saveSettings">Сохранить</button>
          <button class="secondary-button" id="testApi">Проверить API</button>
          <button class="secondary-button" id="loadGuilds">Загрузить серверы</button>
        </div>
        ${renderApiStatus()}
        ${renderAuthStatus()}
        ${state.api.guilds.length ? `
          <div class="form-grid api-picker">
            <div class="field full">
              <label for="guildPicker">Серверы, где есть бот</label>
              <select id="guildPicker">${guildOptions}</select>
            </div>
            ${state.api.textChannels.length ? `
              <div class="field">
                <label for="textChannelPicker">Текстовый канал</label>
                <select id="textChannelPicker">${textOptions}</select>
              </div>
            ` : ""}
            ${state.api.voiceChannels.length ? `
              <div class="field">
                <label for="voiceChannelPicker">Голосовой канал</label>
                <select id="voiceChannelPicker">${voiceOptions}</select>
              </div>
            ` : ""}
            ${state.api.roles.length ? `
              <div class="field full">
                <label for="rolePicker">Роли для reaction roles</label>
                <select id="rolePicker">${roleOptions}</select>
              </div>
            ` : ""}
          </div>
        ` : ""}
        <div class="action-row">
          <button class="secondary-button" data-copy="servers">Скопировать servers</button>
          <button class="ghost-button" data-copy="channels &lt;guild_id&gt;">Скопировать channels</button>
        </div>
      </div>
      <aside>
        <div class="note-box">
          <h3>Где взять ID</h3>
          <p class="muted">При включенном API нажми <strong>Загрузить серверы</strong>. Без API запусти бота и введи в терминале <code>servers</code>, затем <code>channels &lt;guild_id&gt;</code> и <code>roles &lt;guild_id&gt;</code>.</p>
        </div>
      </aside>
    </div>
  `;
}

function renderEmbeds() {
  setHeader("Основное", "Embed-сообщения");
  document.querySelector("#content").innerHTML = renderEmbedsInner();
  bindDynamicForms();
}

function renderEmbedsInner() {
  const channelId = state.settings.textChannelId || "<channel_id>";
  return `
    <div class="workspace">
      <div class="form-box">
        <h2>Конструктор embed</h2>
        <div class="form-grid">
          ${plainField("embedChannel", "ID канала", channelId)}
          ${plainField("embedTitle", "Заголовок", "Правила сервера")}
          ${plainField("embedColor", "Цвет", "#6257ff")}
          <div class="field full">
            <label for="embedDescription">Описание</label>
            <textarea id="embedDescription">Выбери нужную роль, соблюдай правила и уважай участников сервера.</textarea>
          </div>
        </div>
        <div class="action-row">
          <button class="primary-button" id="refreshEmbed">Обновить предпросмотр</button>
          <button class="secondary-button" id="sendEmbed">Отправить через API</button>
          <button class="ghost-button" id="copyEmbedCommand">Копировать команду</button>
        </div>
      </div>
      <aside class="preview-box">
        <div class="preview-title">Предпросмотр</div>
        <div id="embedPreview"></div>
        <pre class="code-output" id="embedCommand"></pre>
      </aside>
    </div>
  `;
}

function renderModerationInner() {
  const guildId = state.settings.guildId || "<guild_id>";
  const textChannelId = state.settings.textChannelId || "<channel_id>";
  const policy = state.api.warnPolicy || defaultWarnPolicy();
  return `
    <div class="section">
      <h2>Быстрые действия</h2>
      <div class="form-box">
        <div class="form-grid">
          ${plainField("clearChannel", "ID канала", textChannelId)}
          ${plainField("clearAmount", "Сколько удалить", "10", "number")}
          ${plainField("modGuild", "ID сервера", guildId)}
          ${plainField("modMember", "Member/User ID", "123456789012345678")}
          <div class="field full">
            <label for="modReason">Причина</label>
            <input id="modReason" value="Причина из панели">
          </div>
        </div>
        <div class="action-row">
          <button class="secondary-button" data-build-mod="clear">Выполнить clear</button>
          <button class="secondary-button" data-build-mod="kick">Выполнить kick</button>
          <button class="danger-button" data-build-mod="ban">Выполнить ban</button>
          <button class="ghost-button" data-build-mod="unban">Выполнить unban</button>
        </div>
        <pre class="code-output" id="modCommand">clear ${textChannelId} 10</pre>
      </div>
    </div>
    <div class="section">
      <h2>Варны и авто-наказания</h2>
      <div class="workspace">
        <div class="form-box">
          <h3>Выдать или проверить варны</h3>
          <div class="form-grid">
            ${plainField("warnGuild", "ID сервера", guildId)}
            ${plainField("warnMember", "Member ID", "123456789012345678")}
            <div class="field full">
              <label for="warnReason">Причина варна</label>
              <input id="warnReason" value="Нарушение правил">
            </div>
          </div>
          <div class="action-row">
            <button class="primary-button" id="issueWarn">Выдать warn</button>
            <button class="secondary-button" id="listWarns">Показать варны</button>
            <button class="danger-button" id="clearWarns">Снять варны</button>
          </div>
          <pre class="code-output" id="warnResult">Здесь появится результат действия.</pre>
        </div>
        <aside class="form-box">
          <h3>Настройка правил</h3>
          <div class="form-grid">
            ${plainField("warnDecayDays", "Через сколько дней спадёт warn", policy.decayDays || 30, "number")}
          </div>
          <div class="tier-list" id="warnTierRows">
            ${renderWarnTierRows(policy)}
          </div>
          <div class="action-row">
            <button class="secondary-button" id="addWarnTier">Добавить порог</button>
            <button class="primary-button" id="saveWarnPolicy">Сохранить правила</button>
          </div>
        </aside>
      </div>
    </div>
  `;
}

function renderWarnTierRows(policy) {
  const tiers = policy.tiers?.length ? policy.tiers : defaultWarnPolicy().tiers;
  return tiers.map((tier, index) => `
    <div class="tier-grid" data-warn-tier="${index}">
      <div class="field">
        <label>Варнов</label>
        <input data-tier-field="warns" type="number" min="1" value="${escapeAttr(tier.warns)}">
      </div>
      <div class="field">
        <label>Действие</label>
        <select data-tier-field="action">
          ${["none", "timeout", "kick", "ban"].map((action) => `<option value="${action}" ${tier.action === action ? "selected" : ""}>${warnActionLabel(action)}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label>Минут мута</label>
        <input data-tier-field="durationMinutes" type="number" min="0" value="${escapeAttr(tier.durationMinutes || 0)}">
      </div>
      <div class="field">
        <label>Название</label>
        <input data-tier-field="label" value="${escapeAttr(tier.label || "")}">
      </div>
      <button class="danger-button" data-remove-warn-tier="${index}" title="Удалить порог">×</button>
    </div>
  `).join("");
}

function warnActionLabel(action) {
  const labels = {
    none: "Только warn",
    timeout: "Мут / timeout",
    kick: "Kick",
    ban: "Ban"
  };
  return labels[action] || action;
}

function renderAutomodInner() {
  const guildId = state.settings.guildId || "<guild_id>";
  return `
    <div class="form-box">
      <h2>Антимат и защита</h2>
      <div class="setting-list">
        <div class="setting-row"><div><strong>antimat_enabled</strong><span>Фильтрация слов из <code>cogs/words.txt</code>.</span></div><button class="toggle on"></button></div>
        <div class="setting-row"><div><strong>AI-модерация</strong><span>Проверка токсичности через OpenAI, если настроен ключ.</span></div><button class="toggle on"></button></div>
        <div class="setting-row"><div><strong>Anti-Raid</strong><span>Ограничение слишком новых аккаунтов.</span></div><button class="toggle on"></button></div>
      </div>
      <div class="form-grid" style="margin-top:16px">
        ${plainField("automodGuild", "ID сервера", guildId)}
        <div class="field full">
          <label for="badWords">Слова через запятую</label>
          <textarea id="badWords">пример, слово, фильтр</textarea>
        </div>
      </div>
      <div class="action-row">
        <button class="secondary-button" id="enableAntimat">Включить antimat</button>
        <button class="secondary-button" id="copyAddWords">Добавить слова</button>
        <button class="ghost-button" id="copyDelWords">Удалить слова</button>
      </div>
    </div>
  `;
}

function renderMusicInner() {
  const guildId = state.settings.guildId || "<guild_id>";
  const textChannelId = state.settings.textChannelId || "<text_channel_id>";
  const voiceChannelId = state.settings.voiceChannelId || "<voice_channel_id>";
  const musicButtons = ["menu", "join", "play", "skip", "shuffle", "jump", "queue", "now", "leave", "stop"]
    .map((name) => {
      const style = name === "stop" ? "danger-button" : ["queue", "now", "leave"].includes(name) ? "ghost-button" : "secondary-button";
      return `<button class="${style}" data-build-music="${name}">${name}</button>`;
    }).join("");
  return `
    <div class="workspace single">
      <div class="form-box">
        <h2>Музыкальная панель</h2>
        <div class="form-grid">
          ${plainField("musicTextChannel", "ID текстового канала для /menu", textChannelId)}
          ${plainField("musicVoiceChannel", "ID голосового канала", voiceChannelId)}
          ${plainField("musicGuild", "ID сервера", guildId)}
          ${plainField("musicQuery", "Поиск или ссылка", "Домик в майнкрафте")}
          ${plainField("musicPosition", "Номер в очереди", "2", "number")}
          ${plainField("musicSeek", "Секунда", "90", "number")}
        </div>
        <div class="action-row">
          ${musicButtons}
        </div>
        <pre class="code-output" id="musicCommand">menu ${textChannelId}</pre>
      </div>
    </div>
  `;
}

function renderReactionRolesInner() {
  const channelId = state.settings.rolesChannelId || state.settings.textChannelId || "<channel_id>";
  return `
    <div class="workspace">
      <div class="form-box">
        <h2>Роли по реакциям</h2>
        <div class="form-grid">
          ${plainField("rrChannel", "ID канала", channelId)}
          ${plainField("rrTitle", "Заголовок", "Выбери игру")}
          <div class="field full">
            <label for="rrDescription">Описание</label>
            <textarea id="rrDescription">Нажми на реакцию ниже, чтобы получить или снять роль.</textarea>
          </div>
        </div>
        <div class="section" style="margin-top:16px">
          <h3>Emoji и роль</h3>
          <div id="reactionRows"></div>
          <div class="action-row">
            <button class="secondary-button" id="addReactionRow">Добавить строку</button>
            <button class="primary-button" id="buildReactionRoles">Собрать команду</button>
          </div>
        </div>
      </div>
      <aside class="preview-box">
        <div class="preview-title">Предпросмотр</div>
        <div id="reactionPreview"></div>
        <pre class="code-output" id="reactionCommand"></pre>
        <div class="action-row">
          <button class="secondary-button" id="executeReactionCommand">Создать через API</button>
          <button class="ghost-button" id="copyReactionCommand">Копировать команду</button>
        </div>
      </aside>
    </div>
  `;
}

function renderLogsInner() {
  const guildId = state.settings.guildId || "<guild_id>";
  const output = state.api.modlog ? formatModlog(state.api.modlog) : "Нажми «Загрузить журнал», чтобы увидеть общий modlog бота и сайта.";
  return `
    <div class="form-box">
      <h2>Логи</h2>
      <p class="muted">Журнал модерации общий для slash-команд, сайта и локальной консоли. Данные читаются из того же <code>data/modlog.json</code>.</p>
      <div class="form-grid">
        ${plainField("modlogGuild", "ID сервера", guildId)}
      </div>
      <div class="action-row">
        <button class="primary-button" id="loadModlog">Загрузить журнал</button>
        <button class="secondary-button" data-copy="/modlog">Копировать /modlog</button>
        <button class="secondary-button" data-copy="/modlog user:@user">Копировать /modlog user</button>
      </div>
      <pre class="code-output" id="modlogResult">${escapeHTML(output)}</pre>
    </div>
  `;
}

function renderDeveloperInner() {
  return `
    <div class="form-box">
      <h2>Панель разработчика</h2>
      <div class="setting-list">
        ${["/dev action:panel", "/dev action:servers", "/dev action:invites", "/dev action:botinfo", "/dev action:shutdown"].map((value) => `
          <div class="setting-row"><div><strong><code>${value}</code></strong><span>Только владелец бота.</span></div><button class="ghost-button" data-copy="${escapeAttr(value)}">Копировать</button></div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderCommands() {
  setHeader("Каталог", "Команды");
  const categories = ["all", ...new Set(commands.map((item) => item.category))];
  const filtered = commands.filter((item) => {
    const categoryOk = state.commandFilter === "all" || item.category === state.commandFilter;
    const text = `${item.name} ${item.description} ${item.usage}`.toLowerCase();
    return categoryOk && text.includes(state.commandSearch.toLowerCase());
  });

  document.querySelector("#content").innerHTML = `
    <div class="toolbar stack">
      <input class="search-box" id="commandSearch" placeholder="Поиск команды" value="${escapeAttr(state.commandSearch)}">
      <div class="segmented">
        ${categories.map((category) => `<button class="chip ${state.commandFilter === category ? "active" : ""}" data-filter-command="${escapeAttr(category)}">${category === "all" ? "Все" : escapeHTML(category)}</button>`).join("")}
      </div>
    </div>
    <div class="command-list">
      ${filtered.length ? filtered.map(renderCommandCard).join("") : `<div class="empty-state">Команды не найдены.</div>`}
    </div>
  `;

  document.querySelector("#commandSearch").addEventListener("input", (event) => {
    state.commandSearch = event.target.value;
    renderCommands();
    document.querySelector("#commandSearch").focus();
  });

  document.querySelectorAll("[data-filter-command]").forEach((button) => {
    button.addEventListener("click", () => {
      state.commandFilter = button.dataset.filterCommand;
      renderCommands();
    });
  });
}

function renderCommandCard(item) {
  return `
    <article class="command-card">
      <div>
        <span class="command-name">${escapeHTML(item.name)}</span>
        <p>${escapeHTML(item.description)}</p>
        <div class="command-meta">Slash-команда: <code>${escapeHTML(item.usage)}</code></div>
        <div class="command-meta">Консоль: <code>${escapeHTML(item.consoleCommand)}</code></div>
      </div>
      <div class="action-row">
        <button class="secondary-button" data-copy="${escapeAttr(item.usage)}">Slash</button>
        <button class="ghost-button" data-copy="${escapeAttr(item.consoleCommand)}">Консоль</button>
      </div>
    </article>
  `;
}

function renderConsole() {
  setHeader("Локальное управление", "Консоль");
  const guildId = state.settings.guildId || "<guild_id>";
  const textChannelId = state.settings.textChannelId || "<channel_id>";
  const voiceChannelId = state.settings.voiceChannelId || "<voice_channel_id>";

  document.querySelector("#content").innerHTML = `
    <div class="workspace">
      <div>
        <div class="note-box section">
          <h2>Команды терминала</h2>
          <p class="muted">Эти команды вводятся в окне, где запущен <code>python bot.py</code>. Сайт помогает собрать точную строку с ID каналов и сервера.</p>
        </div>
        <div class="command-list">
          ${[
            `servers`,
            `channels ${guildId}`,
            `roles ${guildId}`,
            `say ${textChannelId} Привет с сайта`,
            `menu ${textChannelId}`,
            `play ${voiceChannelId} Домик в майнкрафте`,
            `skip ${guildId}`,
            `stop ${guildId}`,
            `rr list ${guildId}`,
            `sync`
          ].map((value) => `
            <article class="command-card">
              <div><span class="command-name">${escapeHTML(value)}</span><p>Готовая команда консоли.</p></div>
              <button class="secondary-button" data-copy="${escapeAttr(value)}">Копировать</button>
            </article>
          `).join("")}
        </div>
      </div>
      <aside>
        ${renderConnectionNote()}
      </aside>
    </div>
  `;
}

function bindDynamicForms() {
  document.querySelector("#saveSettings")?.addEventListener("click", () => {
    syncSettingsFromInputs();
    saveSettings();
    toast("Настройки сохранены в браузере.");
  });

  document.querySelector("#testApi")?.addEventListener("click", testApiConnection);
  document.querySelector("#loadGuilds")?.addEventListener("click", loadApiGuilds);
  document.querySelector("#discordLogin")?.addEventListener("click", () => {
    syncSettingsFromInputs();
    saveSettings();
    const url = window.BotDashboardApi.authUrl(state.settings);
    if (!url) {
      toast("Сначала укажи URL API бота.");
      return;
    }
    location.href = url;
  });
  document.querySelector("#discordLogout")?.addEventListener("click", logoutDashboard);
  document.querySelector("#guildPicker")?.addEventListener("change", (event) => selectApiGuild(event.target.value));
  document.querySelector("#textChannelPicker")?.addEventListener("change", (event) => {
    state.settings.textChannelId = event.target.value;
    saveSettings();
    renderSettings();
  });
  document.querySelector("#voiceChannelPicker")?.addEventListener("change", (event) => {
    state.settings.voiceChannelId = event.target.value;
    saveSettings();
    renderSettings();
  });
  document.querySelector("#rolePicker")?.addEventListener("change", (event) => {
    if (state.reactionRows.length) {
      state.reactionRows[0].role = event.target.value;
      toast("ID роли подставлен в первый ряд reaction roles.");
    }
  });

  document.querySelector("#refreshEmbed")?.addEventListener("click", updateEmbedPreview);
  document.querySelector("#copyEmbedCommand")?.addEventListener("click", () => copyText(updateEmbedPreview()));
  document.querySelector("#sendEmbed")?.addEventListener("click", sendEmbedAction);
  if (document.querySelector("#embedPreview")) updateEmbedPreview();

  document.querySelectorAll("[data-build-mod]").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = buildModerationCommand(button.dataset.buildMod);
      document.querySelector("#modCommand").textContent = value;
      await executeModerationAction(button.dataset.buildMod, value);
    });
  });
  document.querySelector("#issueWarn")?.addEventListener("click", issueWarnAction);
  document.querySelector("#listWarns")?.addEventListener("click", listWarnsAction);
  document.querySelector("#clearWarns")?.addEventListener("click", clearWarnsAction);
  document.querySelector("#saveWarnPolicy")?.addEventListener("click", saveWarnPolicyAction);
  document.querySelector("#loadModlog")?.addEventListener("click", loadModlogAction);
  document.querySelector("#addWarnTier")?.addEventListener("click", () => {
    state.api.warnPolicy = collectWarnPolicy();
    state.api.warnPolicy.tiers.push({ warns: state.api.warnPolicy.tiers.length + 1, action: "timeout", durationMinutes: 30, label: "Новый порог" });
    render();
  });
  document.querySelectorAll("[data-remove-warn-tier]").forEach((button) => {
    button.addEventListener("click", () => {
      state.api.warnPolicy = collectWarnPolicy();
      const index = Number(button.dataset.removeWarnTier);
      state.api.warnPolicy.tiers.splice(index, 1);
      if (!state.api.warnPolicy.tiers.length) state.api.warnPolicy.tiers.push(defaultWarnPolicy().tiers[0]);
      render();
    });
  });

  document.querySelector("#enableAntimat")?.addEventListener("click", enableAntimatAction);
  document.querySelector("#copyAddWords")?.addEventListener("click", () => executeWordsAction("add_words"));
  document.querySelector("#copyDelWords")?.addEventListener("click", () => executeWordsAction("del_words"));

  document.querySelectorAll("[data-build-music]").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = buildMusicCommand(button.dataset.buildMusic);
      document.querySelector("#musicCommand").textContent = value;
      await executeMusicAction(button.dataset.buildMusic, value);
    });
  });

  if (document.querySelector("#reactionRows")) {
    renderReactionRows();
    updateReactionPreview();
  }

  document.querySelector("#addReactionRow")?.addEventListener("click", () => {
    state.reactionRows.push({ emoji: "✨", role: "ID роли" });
    renderReactionRows();
    updateReactionPreview();
  });

  document.querySelector("#buildReactionRoles")?.addEventListener("click", updateReactionPreview);
  document.querySelector("#copyReactionCommand")?.addEventListener("click", () => copyText(updateReactionPreview()));
  document.querySelector("#executeReactionCommand")?.addEventListener("click", executeReactionRolesAction);
}

function syncSettingsFromInputs() {
  ["guildName", "guildId", "textChannelId", "voiceChannelId", "rolesChannelId", "apiUrl", "dashboardToken"].forEach((key) => {
    const input = document.querySelector(`#${key}`);
    if (input) state.settings[key] = input.value.trim();
  });
}

async function testApiConnection() {
  syncSettingsFromInputs();
  saveSettings();
  state.api.status = "loading";
  state.api.message = "Проверяю API...";
  state.api.lastResult = "";
  renderSettings();

  try {
    const data = await window.BotDashboardApi.request(state.settings, "/api/health");
    state.api.auth = data.auth || null;
    state.api.status = "ok";
    state.api.message = `API доступен. Серверов у бота: ${data.guildCount}.`;
    state.api.lastResult = JSON.stringify(data.auth, null, 2);
    await loadApiMe({ silent: true });
  } catch (error) {
    state.api.status = "error";
    state.api.message = "API недоступен.";
    state.api.lastResult = error.message;
  }
  renderSettings();
}

async function loadApiMe(options = {}) {
  try {
    const data = await window.BotDashboardApi.request(state.settings, "/api/me");
    state.api.me = { mode: data.mode, user: data.user || null };
    return state.api.me;
  } catch (error) {
    state.api.me = null;
    if (!options.silent) {
      toast(error.message);
    }
    return null;
  }
}

async function logoutDashboard() {
  syncSettingsFromInputs();
  saveSettings();
  try {
    await window.BotDashboardApi.request(state.settings, "/api/auth/logout", { method: "POST" });
    state.api.me = null;
    state.api.guilds = [];
    state.api.textChannels = [];
    state.api.voiceChannels = [];
    state.api.roles = [];
    state.api.status = "ok";
    state.api.message = "Выход выполнен.";
    state.api.lastResult = "";
  } catch (error) {
    state.api.status = "error";
    state.api.message = "Не удалось выйти.";
    state.api.lastResult = error.message;
  }
  renderSettings();
}

async function loadApiGuilds(options = {}) {
  const keepRoute = Boolean(options.keepRoute);
  const rerender = () => keepRoute ? render() : renderSettings();
  syncSettingsFromInputs();
  saveSettings();
  state.api.status = "loading";
  state.api.message = "Загружаю серверы...";
  state.api.lastResult = "";
  rerender();

  try {
    await loadApiMe({ silent: true });
    const data = await window.BotDashboardApi.request(state.settings, "/api/guilds");
    state.api.guilds = data.guilds || [];
    state.api.status = "ok";
    state.api.message = state.api.guilds.length ? "Серверы загружены." : "API работает, но доступных серверов нет.";
    if (state.api.guilds.length) {
      const selected = state.api.guilds.find((guild) => guild.id === state.settings.guildId) || state.api.guilds[0];
      await selectApiGuild(selected.id, false);
      rerender();
      return;
    }
  } catch (error) {
    state.api.status = "error";
    state.api.message = "Не удалось загрузить серверы.";
    state.api.lastResult = error.message;
  }
  rerender();
}

async function selectApiGuild(guildId, shouldRender = true) {
  const guild = state.api.guilds.find((item) => item.id === guildId);
  if (guild) {
    state.settings.guildName = guild.name;
    state.settings.guildId = guild.id;
  }
  try {
    const [channels, roles, settings, warnPolicy] = await Promise.all([
      window.BotDashboardApi.request(state.settings, `/api/guilds/${guildId}/channels`),
      window.BotDashboardApi.request(state.settings, `/api/guilds/${guildId}/roles`),
      window.BotDashboardApi.request(state.settings, `/api/guilds/${guildId}/settings`),
      window.BotDashboardApi.action(state.settings, "warnings.config.get", guildId, { guildId })
    ]);
    state.api.textChannels = channels.textChannels || [];
    state.api.voiceChannels = channels.voiceChannels || [];
    state.api.roles = roles.roles || [];
    state.api.guildSettings = settings.settings || {};
    state.api.warnPolicy = warnPolicy.result || defaultWarnPolicy();
    if (!state.settings.textChannelId && state.api.textChannels[0]) state.settings.textChannelId = state.api.textChannels[0].id;
    if (!state.settings.voiceChannelId && state.api.voiceChannels[0]) state.settings.voiceChannelId = state.api.voiceChannels[0].id;
    if (!state.settings.rolesChannelId && state.api.textChannels[0]) state.settings.rolesChannelId = state.api.textChannels[0].id;
    state.api.status = "ok";
    state.api.message = `Выбран сервер: ${guild?.name || guildId}.`;
    state.api.lastResult = `Текстовых каналов: ${state.api.textChannels.length}\nГолосовых каналов: ${state.api.voiceChannels.length}\nРолей: ${state.api.roles.length}`;
    saveSettings();
  } catch (error) {
    state.api.status = "error";
    state.api.message = "Не удалось загрузить каналы или роли.";
    state.api.lastResult = error.message;
  }
  if (shouldRender) renderSettings();
}

async function runApiAction(type, guildId, payload, options = {}) {
  const fallback = options.fallback || "";
  if (!window.BotDashboardApi?.isConfigured(state.settings)) {
    if (fallback) await copyText(fallback);
    toast("API не настроен, команда скопирована для терминала.");
    return null;
  }

  if (options.confirmText && !confirm(options.confirmText)) {
    return null;
  }

  try {
    const data = await window.BotDashboardApi.action(state.settings, type, guildId || state.settings.guildId, payload);
    const result = formatApiResult(data.result || data.jumpUrl || "Готово.");
    state.api.status = "ok";
    state.api.message = "Действие выполнено.";
    state.api.lastResult = result;
    toast(result.length > 120 ? "Действие выполнено." : result);
    return data;
  } catch (error) {
    state.api.status = "error";
    state.api.message = "Ошибка API.";
    state.api.lastResult = error.message;
    toast(error.message);
    return null;
  }
}

async function sendEmbedAction() {
  const fallback = updateEmbedPreview();
  await runApiAction("message.embed", state.settings.guildId, {
    textChannelId: valueOf("embedChannel"),
    title: valueOf("embedTitle"),
    description: valueOf("embedDescription"),
    color: valueOf("embedColor")
  }, { fallback });
}

async function executeModerationAction(type, fallback) {
  const guildId = valueOf("modGuild") || state.settings.guildId;
  const memberId = valueOf("modMember");
  const payloads = {
    clear: { textChannelId: valueOf("clearChannel"), amount: valueOf("clearAmount") },
    kick: { guildId, memberId, reason: valueOf("modReason") },
    ban: { guildId, userId: memberId, reason: valueOf("modReason"), deleteMessageDays: 0 },
    unban: { guildId, userId: memberId, reason: valueOf("modReason") }
  };
  await runApiAction(`moderation.${type}`, guildId, payloads[type], {
    fallback,
    confirmText: `Выполнить ${type} на сервере ${guildId}?`
  });
}

async function issueWarnAction() {
  const guildId = valueOf("warnGuild") || state.settings.guildId;
  const memberId = valueOf("warnMember");
  const reason = valueOf("warnReason") || "Без причины";
  const data = await runApiAction("warnings.warn", guildId, { guildId, memberId, reason }, {
    fallback: `/warn member:${memberId} reason:${reason}`,
    confirmText: `Выдать warn участнику ${memberId}?`
  });
  if (data) writeActionResult("warnResult", data.result);
}

async function listWarnsAction() {
  const guildId = valueOf("warnGuild") || state.settings.guildId;
  const memberId = valueOf("warnMember");
  const data = await runApiAction("warnings.list", guildId, { guildId, memberId }, {
    fallback: `/warnings member:${memberId}`
  });
  if (data) writeActionResult("warnResult", formatWarnings(data.result || []));
}

async function clearWarnsAction() {
  const guildId = valueOf("warnGuild") || state.settings.guildId;
  const memberId = valueOf("warnMember");
  const reason = valueOf("warnReason") || "Снято через панель";
  const data = await runApiAction("warnings.clear", guildId, { guildId, memberId, reason }, {
    fallback: `/clearwarns member:${memberId} reason:${reason}`,
    confirmText: `Снять активные варны участника ${memberId}?`
  });
  if (data) writeActionResult("warnResult", data.result);
}

async function saveWarnPolicyAction() {
  const guildId = valueOf("warnGuild") || state.settings.guildId;
  const policy = collectWarnPolicy();
  const data = await runApiAction("warnings.config.set", guildId, { guildId, policy }, {
    fallback: `config set ${guildId} warn_policy <json>`
  });
  if (data?.policy) {
    state.api.warnPolicy = data.policy;
    writeActionResult("warnResult", "Настройки варнов сохранены.");
    render();
  }
}

function collectWarnPolicy() {
  const tiers = [...document.querySelectorAll("[data-warn-tier]")].map((row) => ({
    warns: Number(row.querySelector('[data-tier-field="warns"]').value || 1),
    action: row.querySelector('[data-tier-field="action"]').value,
    durationMinutes: Number(row.querySelector('[data-tier-field="durationMinutes"]').value || 0),
    label: row.querySelector('[data-tier-field="label"]').value.trim()
  }));
  return {
    decayDays: Number(valueOf("warnDecayDays") || 30),
    tiers
  };
}

function formatWarnings(warnings) {
  if (!warnings.length) return "Активных варнов нет.";
  return warnings.map((warning, index) => {
    const reason = warning.reason || "Без причины";
    const expires = warning.expires_at || "без срока";
    return `${index + 1}. ${reason} | спадёт: ${expires}`;
  }).join("\n");
}

async function loadModlogAction() {
  const guildId = valueOf("modlogGuild") || state.settings.guildId;
  if (!window.BotDashboardApi?.isConfigured(state.settings)) {
    await copyText(`/modlog`);
    toast("API не настроен, команда скопирована для Discord.");
    return;
  }

  try {
    const data = await window.BotDashboardApi.request(state.settings, `/api/guilds/${guildId}/modlog`);
    state.api.modlog = data.actions || {};
    writeActionResult("modlogResult", formatModlog(state.api.modlog));
    state.api.status = "ok";
    state.api.message = "Журнал модерации загружен.";
  } catch (error) {
    state.api.status = "error";
    state.api.message = "Не удалось загрузить журнал модерации.";
    state.api.lastResult = error.message;
    writeActionResult("modlogResult", error.message);
    toast(error.message);
  }
}

function formatModlog(actions) {
  const rows = [];
  Object.entries(actions || {}).forEach(([targetId, entries]) => {
    (Array.isArray(entries) ? entries : []).forEach((entry) => {
      rows.push({
        targetId,
        timestamp: entry.timestamp || "",
        action: entry.action || "unknown",
        moderator: entry.moderator_id || "unknown",
        reason: entry.reason || "без причины"
      });
    });
  });

  if (!rows.length) {
    return "Журнал модерации пуст.";
  }

  rows.sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)));
  return rows.slice(-30).reverse().map((entry) => {
    const target = entry.targetId === "0" ? "канал/сервер" : `<@${entry.targetId}>`;
    return `${entry.timestamp} | ${entry.action} | цель: ${target} | модератор: ${entry.moderator} | ${entry.reason}`;
  }).join("\n");
}

function writeActionResult(id, value) {
  const node = document.querySelector(`#${id}`);
  if (node) node.textContent = formatApiResult(value);
}

async function enableAntimatAction() {
  const guildId = valueOf("automodGuild") || state.settings.guildId;
  await runApiAction("config.set", guildId, {
    guildId,
    key: "antimat_enabled",
    value: true
  }, { fallback: `config set ${guildId} antimat_enabled true` });
}

async function executeWordsAction(mode) {
  const guildId = valueOf("automodGuild") || state.settings.guildId;
  const words = document.querySelector("#badWords").value.trim();
  const command = `${mode === "add_words" ? "addword" : "delword"} ${words}`;
  await runApiAction(`automod.${mode}`, guildId, { guildId, words }, { fallback: command });
}

async function executeMusicAction(type, fallback) {
  const guildId = valueOf("musicGuild") || state.settings.guildId;
  const payloads = {
    menu: { textChannelId: valueOf("musicTextChannel") },
    join: { voiceChannelId: valueOf("musicVoiceChannel") },
    play: { voiceChannelId: valueOf("musicVoiceChannel"), query: valueOf("musicQuery") },
    skip: { guildId },
    shuffle: { guildId },
    jump: { guildId, position: valueOf("musicPosition") },
    queue: { guildId },
    now: { guildId },
    leave: { guildId },
    stop: { guildId }
  };
  await runApiAction(`music.${type}`, guildId, payloads[type], {
    fallback,
    confirmText: ["stop", "leave"].includes(type) ? `Выполнить ${type} на сервере ${guildId}?` : ""
  });
}

async function executeReactionRolesAction() {
  const fallback = updateReactionPreview();
  const mappings = state.reactionRows
    .filter((row) => row.emoji && row.role)
    .map((row) => ({ emoji: row.emoji, roleId: row.role }));
  if (mappings.some((row) => !/^\d{15,25}$/.test(row.roleId))) {
    toast("Для API укажи ID роли, не название. Названия можно только копировать в консольную команду.");
    await copyText(fallback);
    return;
  }
  await runApiAction("reaction_roles.create", state.settings.guildId, {
    textChannelId: valueOf("rrChannel"),
    title: valueOf("rrTitle"),
    description: valueOf("rrDescription"),
    mappings
  }, { fallback });
}

function formatApiResult(value) {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function updateEmbedPreview() {
  const channel = valueOf("embedChannel");
  const title = valueOf("embedTitle");
  const description = valueOf("embedDescription");
  const color = valueOf("embedColor") || "#6257ff";
  const command = `embed ${channel} | ${title} | ${description.replace(/\n/g, " ")}`;

  document.querySelector("#embedPreview").innerHTML = `
    <div class="discord-message">
      <div class="avatar"></div>
      <div class="message-body">
        <strong>Панель бота</strong><small>сейчас</small>
        <div class="embed-preview" style="border-left-color:${escapeAttr(color)}">
          <h3>${escapeHTML(title)}</h3>
          <p>${escapeHTML(description)}</p>
        </div>
      </div>
    </div>
  `;
  document.querySelector("#embedCommand").textContent = command;
  return command;
}

function buildModerationCommand(type) {
  const channel = valueOf("clearChannel");
  const amount = valueOf("clearAmount");
  const guild = valueOf("modGuild");
  const member = valueOf("modMember");
  const reason = valueOf("modReason");

  const variants = {
    clear: `clear ${channel} ${amount}`,
    kick: `kick ${guild} ${member} ${reason}`,
    ban: `ban ${guild} ${member} ${reason}`,
    unban: `unban ${guild} ${member} ${reason}`
  };
  return variants[type];
}

function buildMusicCommand(type) {
  const textChannel = valueOf("musicTextChannel");
  const voiceChannel = valueOf("musicVoiceChannel");
  const guild = valueOf("musicGuild");
  const query = valueOf("musicQuery");
  const position = valueOf("musicPosition");

  const variants = {
    menu: `menu ${textChannel}`,
    join: `join ${voiceChannel}`,
    play: `play ${voiceChannel} ${query}`,
    skip: `skip ${guild}`,
    shuffle: `shuffle ${guild}`,
    jump: `jump ${guild} ${position}`,
    queue: `queue ${guild}`,
    now: `now ${guild}`,
    leave: `leave ${guild}`,
    stop: `stop ${guild}`
  };
  return variants[type];
}

function renderReactionRows() {
  const container = document.querySelector("#reactionRows");
  container.innerHTML = state.reactionRows.map((row, index) => `
    <div class="reaction-line" data-row="${index}">
      <input value="${escapeAttr(row.emoji)}" aria-label="Emoji">
      <input value="${escapeAttr(row.role)}" aria-label="ID роли или имя роли">
      <button class="danger-button" title="Удалить">×</button>
    </div>
  `).join("");

  container.querySelectorAll(".reaction-line").forEach((line) => {
    const index = Number(line.dataset.row);
    const inputs = line.querySelectorAll("input");
    inputs[0].addEventListener("input", () => {
      state.reactionRows[index].emoji = inputs[0].value.trim();
      updateReactionPreview();
    });
    inputs[1].addEventListener("input", () => {
      state.reactionRows[index].role = inputs[1].value.trim();
      updateReactionPreview();
    });
    line.querySelector("button").addEventListener("click", () => {
      state.reactionRows.splice(index, 1);
      renderReactionRows();
      updateReactionPreview();
    });
  });
}

function updateReactionPreview() {
  const channel = valueOf("rrChannel");
  const title = valueOf("rrTitle");
  const description = valueOf("rrDescription");
  const mappings = state.reactionRows
    .filter((row) => row.emoji && row.role)
    .map((row) => `${row.emoji}=${row.role}`)
    .join("; ");
  const command = `rr create ${channel} | ${title} | ${description.replace(/\n/g, " ")} | ${mappings}`;

  document.querySelector("#reactionPreview").innerHTML = `
    <div class="discord-message">
      <div class="avatar"></div>
      <div class="message-body">
        <strong>Панель бота</strong><small>сейчас</small>
        <div class="embed-preview">
          <h3>${escapeHTML(title)}</h3>
          <p>${escapeHTML(description)}</p>
          <div class="reaction-chip-list">
            ${state.reactionRows.map((row) => `<span class="reaction-chip">${escapeHTML(row.emoji || "•")} <span>${escapeHTML(row.role || "role")}</span></span>`).join("")}
          </div>
        </div>
      </div>
    </div>
  `;
  document.querySelector("#reactionCommand").textContent = command;
  return command;
}

function commandDescription(name) {
  const normalized = name.split(" ")[0] === "/reactionroles" ? name : name.split(" ")[0];
  return commands.find((item) => item.name === name || item.name === normalized)?.description || "Команда бота.";
}

function field(id, label, value, placeholder = "", type = "text") {
  return `
    <div class="field">
      <label for="${id}">${label}</label>
      <input id="${id}" type="${type}" value="${escapeAttr(value)}" placeholder="${escapeAttr(placeholder)}">
    </div>
  `;
}

function plainField(id, label, value, type = "text") {
  return `
    <div class="field">
      <label for="${id}">${label}</label>
      <input id="${id}" type="${type}" value="${escapeAttr(value)}">
    </div>
  `;
}

function valueOf(id) {
  return document.querySelector(`#${id}`)?.value.trim() || "";
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  toast("Скопировано.");
}

function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2200);
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHTML(value).replaceAll("`", "&#096;");
}
