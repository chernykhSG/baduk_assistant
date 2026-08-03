# Findings — исследования и обоснования решений

Здесь хранятся исходные основания для решений в `docs/ARCHITECTURE.md` и `task_plan.md` — чтобы при восстановлении контекста не пересобирать рассуждение заново.

## Сравнение открытых Go-движков/GUI (стек)

Полная таблица — в `docs/ARCHITECTURE.md` («Сравнение открытых движков/GUI и рекомендация по стеку»). Кратко: ни один проект не форкается целиком.

- Sabaki (Electron/Preact) — удобный веб-стек для плагинов, но заточен на GTP, не на batch Analysis Engine.
- KaTrain (Python/Kivy) — родная интеграция с Analysis Engine и обучающий UX, но Kivy несовместим с веб-based UI-плагинами.
- q5Go (C++/Qt) — полнофункционален, но GPL ограничивает лицензионную гибкость плагинного API.
- Lizzie — не рекомендован сообществом, устарел.
- Ogatak (Electron/JS) — лучший референс IPC-архитектуры вокруг Analysis Engine, но тонкий однофункциональный вьюер без слоя данных/плагинов/LLM.
- GoReviewPartner (Python-скрипт) — подтверждает Python как типичный язык для batch-review поверх KataGo, не основа для GUI.

**Вывод**: Electron+TS frontend (вдохновляясь Sabaki/Ogatak) + Python backend (LangChain/LlamaIndex/RAG-экосистема) — гибридная two-process архитектура.

## UI/UX-ревью (скилл `ui-ux-pro-max`)

Инструмент: `search.py` скила (после установки Python 3.12.10 у пользователя — заработал; до этого была нерабочая Windows Store заглушка `python.exe`).

- **Продуктовые аналоги** (для дизайн-системы): ближайшие совпадения в базе — Analytics Dashboard, Real-Time/Operations, Productivity Tool. Все три сходятся на **Dark Mode (OLED)** — совпадает с практикой похожих инструментов (Ogatak, KaTrain, Lizzie: длинные сессии разбора партий).
- **Палитра-стартер** (совпадение "Financial Dashboard", ближайшее к data-dense аналитическому инструменту):
  ```
  --color-background:   #020617
  --color-surface:      #0E1223
  --color-primary:      #0F172A
  --color-foreground:   #F8FAFC
  --color-muted-fg:     #94A3B8
  --color-border:       #334155
  --color-accent:       #22C55E   /* позитивный winrate/статус */
  --color-destructive:  #EF4444   /* потеря очков/ошибка */
  ```
  Не проверено поверх самой доски (чёрные/белые камни + оверлеи) — отдельная задача Фазы 1, т.к. это специфика доски Go, не общий UI-кейс.
- **Типографика**: пара "Dashboard Data" — Fira Code (числа/координаты: winrate, scoreLead, visits, PV, паспорт-метрики) + Fira Sans (проза LLM-панели). Один шрифтовой вендор — меньше веса бандла.
- **Ownership heatmap**: база явно отмечает — heatmap без pattern/numeric-фолбэка не проходит accessibility для дальтоников. Решение: cool→hot (blue→red) градиент + числовое значение по hover/клику + легенда со шкалой делений — обязательная часть контракта `registerBoardOverlay`, не опциональная доработка.
- **Winrate/score-график**: Line Chart подтверждён; при нескольких сериях различать стилем линии (solid/dashed/dotted), не только цветом; нужна переключаемая табличная a11y-альтернатива.
- **Player Passport dashboard**: стиль Drill-Down Analytics + Comparative; тренд по времени → line/area chart; сравнение категорий таксономии → bar chart, **не pie** — таксономия расширяется плагинами (`register_metric_extractor`), число категорий гарантированно превысит порог читаемости pie.
- **Клавиатурная навигация** — архитектурное требование (навигация по дереву вариаций, переключение панелей), не деталь реализации; десктопный аналитический инструмент подразумевает keyboard-first workflow (как в Sabaki/Ogatak).
- **Settings UI** — прогрессивное раскрытие сложности; core-разделы (KataGo-профили, LLM-провайдер, RAG-источники, Plugin Manager) организуются как отдельные секции через тот же механизм `registerSettingsSection`, что и у плагинов.
- **LLM Explanation Panel** — ширина колонки 60–75 символов; цитаты RAG разворачиваемые, не обрезанные; подсветка ходов доступна не только по hover, но и по клику/клавиатуре; потоковая генерация — skeleton/streaming-курсор, не блокирующий спиннер.

Всё это уже перенесено в `docs/ARCHITECTURE.md` § «UI/UX-принципы фронтенда».

## UI-фреймворк фронтенда — решение

Сравнивались: Preact, React, Svelte, Vanilla TS + Web Components (методология — Plan-агент, см. историю сессии).

| Кандидат | Совместимость с Shudan (Preact-native) | Экосистема для data-dense дашбордов | Итог |
|---|---|---|---|
| **Preact** | Нативная — тот же reconciler, реальная композиция | Через `preact/compat` доступна экосистема React на одном рантайме | ✅ Выбран |
| React | Требует `preact/compat`-алиас (= по факту Preact) либо императивный dual-mount Shudan как отдельного рантайма | Крупнейшая номинально, но цена интеграции с Shudan реальна | Отклонён |
| Svelte | Нет пути интеграции — архитектурно не пересекается с Preact VDOM, тот же dual-mount, что у React | Нет аналога `preact/compat`, чтобы одолжить экосистему | Отклонён |
| Vanilla + Web Components | Тот же dual-mount для Shudan, но локально (`customElements.define`) | Самая тонкая экосистема для форм/дашбордов — велосити-цена | Отклонён для ядра, но **эта форма — правильный контракт для плагинов** |

**Ключевой инсайт**: выбор фреймворка ядра ("на чём пишет ядро") и контракт для плагинов ("что обязан отдать плагин") — не один и тот же вопрос, вопреки первоначальной формулировке в архитектуре ("либо Preact для всего, либо framework-agnostic контракт"). Правильный ответ — оба одновременно:

- **Ядро фронтенда — Preact** (обоснование выше + `@preact/signals` подходит для потокового характера обновлений: WebSocket-анализ, LLM-токены).
- **Plugin-контракт — framework-agnostic, DOM/Custom Element** (`registerAnalysisPanel`/`registerBoardOverlay`/`registerSettingsSection` принимают DOM-узел, не Preact VNode) — это единственная форма, которая переживает уже обещанный sandboxed-режим (iframe/BrowserView + postMessage), т.к. Preact VNode не сериализуется через postMessage, а DOM/данные — да.
- Trusted и sandboxed режимы — один контракт, два транспорта (properties+events напрямую на DOM либо через postMessage-мост с шимом).
- Design-tokens (CSS custom properties) framework-agnostic, наследуются по DOM, но не пересекают границу iframe → Plugin Host обязан явно прокидывать resolved-токены в iframe (расширение того же postMessage-моста, не новый механизм).

Оговорка на будущее: `preact/compat` не покрывает 100% API React (Suspense-for-data-fetching, часть `react-dom/client`) — конкретные React-only библиотеки (напр. shadcn/Radix) проверяются точечно в Фазе 1, а не считаются совместимыми по умолчанию.

Всё перенесено в `docs/ARCHITECTURE.md` (§ Frontend/UI, § Плагинная архитектура, § UI/UX-принципы фронтенда).

## Открытые вопросы

_Нет на данный момент._
