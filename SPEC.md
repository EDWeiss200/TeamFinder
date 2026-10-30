# Техническая спецификация и архитектура платформы TeamFinder (TeamTinder / Drill Flex)

> **Назначение документа:** данный файл является главным источником правды (Single Source of Truth) для разработки бэкенда, фронтенда и Telegram-бота платформы автоматизации студенческих хакатонов и мероприятий. Документ оптимизирован для использования в качестве системного контекста при разработке с помощью AI-ассистентов (Cursor, Windsurf, Claude, ChatGPT).

---

## 1. Обзор проекта и ключевые концепции

**TeamFinder (рабочие названия — TeamTinder / Drill Flex)** — веб-платформа в связке с Telegram-ботом для проведения вузовских и городских хакатонов. Платформа решает проблему хаоса в Telegram-чатах и ручного ведения Excel-таблиц организаторами.

### 1.1. Роли пользователей в системе
1. **`PARTICIPANT` (участник / студент):**
   * заполняет единый профиль (ФИО, никнейм, вуз/институт, например `СФУ ИКИТ`, учебная группа, курс, стек/роли, био, ссылки на TG, VK и GitHub);
   * просматривает афишу мероприятий на главной странице или переходит по прямой ссылке от организатора;
   * регистрируется на мероприятие, создает команду (становится капитаном) или ищет существующую команду.
2. **`ORGANIZER` (организатор):**
   * создает и редактирует свои мероприятия, настраивает лимиты команд и дедлайны (доступ разграничен: организатор управляет только теми событиями, где он указан как `organizer_id`, либо если он `is_superuser`);
   * видит дашборд своего хакатона в реальном времени (количество участников, сформированные команды, участники без команд);
   * запускает алгоритм автоматического распределения одиночек («умный матчинг»);
   * имеет права ручного управления составами команд (God Mode) в рамках своего мероприятия и делает таргетированные рассылки через Telegram-бота;
   * выгружает сводные отчеты в формате `.xlsx` (Excel).
3. **`ADMIN` (супер-администратор / `is_superuser=True` в `fastapi-users`):**
   * выдает права роли `ORGANIZER` представителям вуза и управляет глобальными справочниками.

---

## 2. Анализ UI/UX макетов и архитектурные решения по экранам

На основе предоставленных дизайн-макетов заложены следующие архитектурные механизмы:

### 2.1. Главная страница и каталог событий (афиша как на Codenrock)
* **Верхний Hero-баннер (карусель):** на макетах представлен слайдер ключевых событий (синий баннер «О! Хакатон», оранжевый «Баннер другого события»). В таблицу `events` добавляются поля `is_featured` (выводить ли в слайдер), `banner_url` и `theme_color` (HEX-код фона баннера).
* **Блок «Ваше текущее событие»:** если авторизованный студент уже зарегистрирован на активный хакатон, на главной странице отображается виджет быстрого перехода к его текущему мероприятию.
* **Каталог «Все события / Доступные события»:** карточки содержат название, краткое описание, даты регистрации, даты проведения и допустимый размер команды (например, `1–5 человек`).
* **Публичные и закрытые ивенты:** поле `is_public` позволяет публиковать крупные хакатоны на главной странице (`is_public = True`) или скрывать локальные кафедральные соревнования (`is_public = False`), доступ к которым возможен только по прямой ссылке-приглашению (`invite_code`).

### 2.2. Профиль участника
* Содержит аватар, имя и фамилию, никнейм (например, `Ghostrai666`), теги навыков (`дизайн`, `C#`, `бэк`), тег принадлежности к вузу/институту (`сфу икит`), блок «О себе» (`bio`), кнопки-ссылки на Telegram и VK, а также блок «Ваши события» (история и активные регистрации).

### 2.3. Страница события и механика тегов «Ищем» / «Уже есть»
* **Инфо-панель события:** отображает организатора, теги формата (`Идёт`, `Очно`, `Хакатон`, `Веб-разработка`, `Дизайн`), 4 карточки дат/лимитов (`Конец регистрации`, `Начало мероприятия`, `Конец мероприятия`, `Размер команды 3-5`) и подробное Markdown-описание кейса и этапов.
* **Форма «Создать команду»:** содержит поля `название`, `кол-во людей` (`max_members`, в пределах лимитов хакатона), выбор тегов `вы ищете людей` (`needed_roles`) и кнопку приглашения участников.
* **Карточка команды (например, «Drill Flex»):**
  * отображает аватарки участников (у капитана — иконка короны), счетчик `3/5 человек`, описание идеи команды;
  * **две группы тегов ролей:**
    * **`Ищем` (`needed_roles`):** роли, которых не хватает команде (задаются капитаном при создании/редактировании);
    * **`Уже есть` (`existing_roles`):** динамически вычисляемый список ролей уже вступивших участников команды. Когда фронтендер вступает в команду, его роль автоматически попадает в зеленый список «Уже есть», а из списка «Ищем» убирается одна открытая позиция фронтендера.

### 2.4. Единый пайплайн поиска: заявки от одиночек + приглашения от капитанов
На макетах присутствуют два встречных сценария:
1. Одиночка смотрит список команд и нажимает **«Откликнуться»** (Экран 2).
2. Капитан открывает каталог свободных участников («Пригласить участников в команду», Экран 3) и приглашает понравившегося человека.

**Архитектурное решение (Unified Request State Machine):**
Вместо двух разных таблиц используется единая таблица `team_requests`, которая поддерживает двойное подтверждение (финальное решение всегда за одиночкой):
* **Сценарий А (одиночка откликается в команду):**
  1. Участник жмет «Откликнуться» и указывает роль (`target_role`) $\rightarrow$ создается запись со статусом `PENDING_CAPTAIN`. До решения капитана участник может отозвать отклик $\rightarrow$ статус переходит в `CANCELLED`.
  2. Капитану в Telegram (и на сайт) приходит уведомление. Капитан может отклонить заявку $\rightarrow$ `REJECTED`, либо одобрить $\rightarrow$ статус меняется на `PENDING_USER` (оффер отправлен участнику, но место в команде еще жестко не забронировано).
  3. Участнику приходит уведомление: *«Команда Drill Flex готова принять тебя! Подтверди вступление»*. Участник может отказаться $\rightarrow$ `REJECTED`, либо нажать «Вступить» $\rightarrow$ статус `ACCEPTED`, все остальные активные заявки этого участника автоматически переходят в `CANCELLED`.
* **Сценарий Б (капитан сам приглашает участника из каталога на Экране 3):**
  1. Капитан жмет «Пригласить» на карточке свободного участника $\rightarrow$ запись создается **сразу** в статусе `PENDING_USER`! Пока участник не ответил, капитан может отозвать инвайт $\rightarrow$ статус `CANCELLED`.
  2. Участнику в Telegram прилетает инвайт. Он может отклонить инвайт $\rightarrow$ `REJECTED`, либо нажать «Вступить» $\rightarrow$ статус `ACCEPTED`.
* **Сценарий В (прямая инвайт-ссылка для друзей):**
  1. Капитан копирует секретную ссылку команды `/events/{id}/join-team?token={invite_token}` и кидает друзьям в личку.
  2. Переход по ссылке сразу добавляет участника в команду (`ACCEPTED`) без промежуточных подтверждений, если в команде есть свободные места.

---

## 3. Технический стек и архитектура (Clean Architecture + FastAPI Users + UnitOfWork)

### 3.1. Стек технологий
* **Язык:** Python 3.11+
* **Web-фреймворк:** FastAPI (асинхронный REST API, валидация через Pydantic v2)
* **Авторизация и управление пользователями:** `fastapi-users[sqlalchemy]` (JWT Strategy + кастомные поля профиля)
* **База данных:** PostgreSQL 16 + драйвер `asyncpg`
* **ORM и миграции:** SQLAlchemy 2.0 (`AsyncSession`, `Mapped`, `mapped_column`) + Alembic
* **Telegram-бот:** Aiogram 3.x
* **Генерация отчетов:** `openpyxl` (экспорт в `.xlsx`)
* **Инфраструктура и CI/CD:** Docker, Docker Compose, GitHub Actions, линтер `ruff`, тесты `pytest` + `pytest-asyncio` + `httpx`.

### 3.2. Файловая структура проекта (на базе шаблона `backend/src/`)
Веб-сервер (`FastAPI`) и бот (`Aiogram`) живут в папке `backend/src/` и используют единый слой сервисов, репозиториев и `UnitOfWork`.

```text
TeamTinder/
└── backend/
    ├── src/
    │   ├── api/                        # Слой представления (роутеры FastAPI)
    │   │   ├── dependencies.py         # Фабрики сервисов с инъекцией UnitOfWork и проверкой ролей
    │   │   ├── exception_handlers.py   # Маппинг доменных ошибок Сервисов в HTTP-коды (400, 403, 404, 409)
    │   │   ├── user_router.py          # Профиль, события юзера и генерация ссылки ТГ
    │   │   ├── event_router.py         # Афиша, страница хакатона, регистрация, каталог одиночек
    │   │   ├── team_router.py          # Создание команд, инвайт-ссылки, выход, кик
    │   │   ├── request_router.py       # Отклики, инвайты от капитана, подтверждения
    │   │   └── organizer_router.py     # Панель организатора, умный матчинг, рассылки, Excel
    │   ├── auth/                       # Модуль авторизации fastapi-users
    │   │   ├── auth.py                 # Bearer/Cookie транспорт, JWTStrategy, auth_backend
    │   │   ├── database.py             # Адаптер get_user_db (импортирует сессию из src/database/database.py)
    │   │   ├── manager.py              # UserManager и get_user_manager
    │   │   └── schemas.py              # Схемы UserRead, UserCreate, UserUpdate для fastapi-users
    │   ├── bot/                        # Слой представления Telegram-бота (Aiogram 3.x)
    │   │   ├── handlers/               # Обработчики /start и инлайн-кнопок (одобрить/подтвердить/отклонить)
    │   │   ├── keyboards/              # Генераторы инлайн-клавиатур
    │   │   ├── sender.py               # Безопасный рассыльщик с троттлингом (защита от 429 Too Many Requests)
    │   │   └── main.py                 # Точка входа для запуска контейнера бота
    │   ├── database/
    │   │   └── database.py             # Единый engine, async_session_maker и декларативный Base
    │   ├── migrations/                 # Миграции базы данных Alembic
    │   │   ├── versions/
    │   │   ├── env.py
    │   │   └── script.py.mako
    │   ├── models/                     # Модели таблиц SQLAlchemy 2.0
    │   │   ├── __init__.py             # Экспорт всех моделей для Alembic
    │   │   ├── enums.py                # Все Enum-классы проекта
    │   │   ├── user.py                 # Модель User (наследуется от SQLAlchemyBaseUserTableUUID и Base)
    │   │   ├── event.py                # Модели Event и EventRegistration
    │   │   ├── team.py                 # Модели Team и TeamRequest
    │   │   └── submission.py           # Модель Submission
    │   ├── repositories/               # Репозитории таблиц (наследники SQLAlchemyRepository)
    │   │   ├── user_repo.py
    │   │   ├── event_repo.py
    │   │   ├── registration_repo.py
    │   │   ├── team_repo.py
    │   │   ├── request_repo.py
    │   │   └── submission_repo.py
    │   ├── schemas/                    # Pydantic-схемы (DTO для запросов и ответов API)
    │   │   ├── event.py
    │   │   ├── team.py
    │   │   └── submission.py
    │   ├── services/                   # Слой бизнес-логики (принимает uow в __init__)
    │   │   ├── user_services.py        # Профиль и привязка Telegram
    │   │   ├── event_services.py       # Управление событиями и регистрацией на хакатон
    │   │   ├── team_services.py        # Вся логика команд, заявок, инвайтов, выходов и смены капитана
    │   │   ├── matching_services.py    # Алгоритм умного распределения одиночек
    │   │   └── export_services.py      # Генерация Excel-таблиц (.xlsx) для организатора
    │   ├── utils/                      # Базовые абстракции и паттерны
    │   │   ├── repository.py           # AbstractRepository и SQLAlchemyRepository (принимает session в __init__)
    │   │   ├── uow.py                  # IUnitOfWork и UnitOfWork (управление транзакциями)
    │   │   └── exceptions.py           # Кастомные доменные исключения (TeamIsFullError и др.)
    │   ├── config.py                   # Конфигурация приложения (чтение .env)
    │   └── main.py                     # Точка входа FastAPI + подключение роутеров и CORSMiddleware
    ├── tests/                          # Интеграционные и юнит-тесты (pytest)
    ├── .env
    ├── alembic.ini
    ├── requirements.txt
    ├── Dockerfile
    └── docker-compose.yml
```

### 3.3. Паттерн взаимодействия: `Router -> Depends(Service(UnitOfWork)) -> Repository`

В проекте используется инъекция `UnitOfWork` непосредственно в конструктор `__init__` каждого сервиса. Это позволяет **не передавать `uow` аргументом в каждый метод сервиса** и сохраняет роутеры максимально чистыми.

#### 1. Базовый репозиторий (`src/utils/repository.py`)
Репозиторий получает активную сессию `AsyncSession` от `UnitOfWork` и **не делает `session.commit()` внутри своих методов**:
```python
class SQLAlchemyRepository(AbstractRepository):
    model = None

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_one(self, data: dict):
        stmt = insert(self.model).values(**data).returning(self.model)
        res = await self.session.execute(stmt)
        return res.scalar_one()

    async def find_filter(self, filters: list):
        stmt = select(self.model).where(*filters)
        res = await self.session.execute(stmt)
        return res.scalars().all()
```

#### 2. Контекстный менеджер `UnitOfWork` (`src/utils/uow.py`)
При входе в блок `async with self.uow:` создается одна сессия БД, которая раздается всем репозиториям:
```python
class UnitOfWork(IUnitOfWork):
    def __init__(self):
        self.session_factory = async_session_maker

    async def __aenter__(self):
        self.session = self.session_factory()
        self.users = UserRepository(self.session)
        self.events = EventRepository(self.session)
        self.registrations = RegistrationRepository(self.session)
        self.teams = TeamRepository(self.session)
        self.requests = RequestRepository(self.session)
        self.submissions = SubmissionRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
```

#### 3. Сервисный слой (`src/services/user_services.py`)
Сервис принимает `uow: IUnitOfWork` один раз в `__init__` и сохраняет его в `self.uow`:
```python
class UserServices:
    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    async def get_user_by_id(self, user_id: UUID):
        async with self.uow:
            filters = [self.uow.users.model.id == user_id]
            user = await self.uow.users.find_filter(filters)
            return user
```

#### 4. Фабрики зависимостей (`src/api/dependencies.py`) и Роутеры (`src/api/user_router.py`)
В `dependencies.py` создаются функции-провайдеры сервисов:
```python
def get_uow() -> IUnitOfWork:
    return UnitOfWork()

def user_service(uow: IUnitOfWork = Depends(get_uow)) -> UserServices:
    return UserServices(uow)

def team_service(uow: IUnitOfWork = Depends(get_uow)) -> TeamServices:
    return TeamServices(uow)
```
Благодаря этому код роутеров (`src/api/user_router.py`) остается предельно лаконичным:
```python
@router.get("")
async def get_info_user(
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    return await service.get_user_by_id(user.id)
```
А при вызове этого же сервиса из обработчиков Telegram-бота (`src/bot/handlers/`) достаточно написать:
```python
service = TeamServices(UnitOfWork())
await service.captain_approve_request(request_id=req_id, captain_id=captain.id)
```

---

## 4. Схема базы данных (PostgreSQL)

### 4.1. Перечисления (`src/models/enums.py`)
* **`UserRole`:** `PARTICIPANT = "participant"`, `ORGANIZER = "organizer"`, `ADMIN = "admin"`
* **`EventStatus`:** 
  * `DRAFT = "draft"` (черновик, виден только организатору)
  * `REGISTRATION = "registration"` (открыта регистрация, создание команд и переходы)
  * `TEAM_LOCK = "team_lock"` (составы команд заморожены, идет работа над задачей)
  * `SUBMISSION = "submission"` (открыт прием ссылок на репозитории и презентации)
  * `FINISHED = "finished"` (мероприятие завершено, архив)
* **`EventFormat`:** `OFFLINE = "offline"`, `ONLINE = "online"`, `HYBRID = "hybrid"`
* **`TeamRequestStatus`:** `PENDING_CAPTAIN = "pending_captain"`, `PENDING_USER = "pending_user"`, `ACCEPTED = "accepted"`, `REJECTED = "rejected"`, `CANCELLED = "cancelled"`
* **`TeamRequestType`:** `APPLICATION = "application"` (отклик от участника), `INVITE = "invite"` (приглашение от капитана)

### 4.2. Таблицы и поля

#### 1. Таблица `users` (`src/models/user.py` — совместима с `fastapi-users`)
| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Уникальный ID (из `SQLAlchemyBaseUserTableUUID`) |
| `email` | `VARCHAR(320)` (Unique) | Email для входа (из `SQLAlchemyBaseUserTableUUID`) |
| `hashed_password` | `VARCHAR(1024)` | Хэш пароля (из `SQLAlchemyBaseUserTableUUID`) |
| `is_active` | `BOOLEAN` | Активен ли аккаунт (по умолчанию `True`) |
| `is_superuser` | `BOOLEAN` | Супер-админ системы (по умолчанию `False`) |
| `is_verified` | `BOOLEAN` | Подтвержден ли email (по умолчанию `False`) |
| `role` | `Enum(UserRole)` | Роль в системе (по умолчанию `PARTICIPANT`) |
| `full_name` | `VARCHAR(255)` | Имя и фамилия (для выгрузки в Excel деканату) |
| `nickname` | `VARCHAR(100)` (Nullable) | Отображаемый никнейм (например, `Ghostrai666`) |
| `avatar_url` | `VARCHAR(512)` (Nullable) | Ссылка на аватарку |
| `university` | `VARCHAR(255)` (Nullable) | Вуз / институт (например, `СФУ ИКИТ`) |
| `study_group` | `VARCHAR(100)` (Nullable) | Учебная группа (например, `КИ25-20Б`) |
| `course` | `SMALLINT` (Nullable) | Курс обучения ($1\dots6$) |
| `bio` | `TEXT` (Nullable) | Описание «О себе» |
| `skills` | `ARRAY(VARCHAR)` | Массив тегов навыков (`["дизайн", "C#", "бэк"]`, default `[]`) |
| `primary_role` | `VARCHAR(100)` (Nullable) | Основная роль (`"фронт"`, `"бэк"`, `"дизайн"`, `"ML"`, `"аналитик"`) |
| `vk_url` | `VARCHAR(255)` (Nullable) | Ссылка на профиль ВКонтакте |
| `github_url` | `VARCHAR(255)` (Nullable) | Ссылка на профиль GitHub |
| `telegram_id` | `BIGINT` (Unique, Nullable) | Цифровой ID пользователя в Telegram (для пушей от бота) |
| `telegram_username`| `VARCHAR(100)` (Nullable) | Ник в Telegram без `@` (для кнопки «Написать» на сайте) |
| `telegram_bind_token`| `VARCHAR(64)` (Nullable, Unique)| Одноразовый токен для привязки бота через `/start` |
| `is_bot_active` | `BOOLEAN` | `True`, если бот привязан и не заблокирован пользователем |
| `created_at` | `TIMESTAMPTZ` | Дата регистрации (`server_default=func.now()`) |

#### 2. Таблица `events` (`src/models/event.py` — мероприятия / хакатоны)
| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Уникальный ID события |
| `title` | `VARCHAR(255)` | Название (например, `О! Хакатон` или `Yandex Cup 2026`) |
| `short_description`| `VARCHAR(500)` | Краткое описание для карточки на главной странице |
| `description_md` | `TEXT` | Полное описание (Markdown: о событии, для кого, этапы, контакты) |
| `organizer_name` | `VARCHAR(255)` | Отображаемое имя организатора (например, `Яндекс` или `СФУ`) |
| `organizer_id` | `UUID` (FK -> `users.id`) | Создатель мероприятия |
| `status` | `Enum(EventStatus)` | Текущий этап жизненного цикла (default `REGISTRATION`) |
| `format` | `Enum(EventFormat)` | `OFFLINE`, `ONLINE`, `HYBRID` |
| `tags` | `ARRAY(VARCHAR)` | Теги тематики (`["Хакатон", "Веб-разработка", "Дизайн"]`) |
| `banner_url` | `VARCHAR(512)` (Nullable) | Картинка для карточки и шапки |
| `theme_color` | `VARCHAR(7)` | HEX-цвет баннера на главной (например, `#0044FF` или `#FF5733`) |
| `is_public` | `BOOLEAN` | Показывать ли в общем каталоге на главной странице |
| `is_featured` | `BOOLEAN` | Выводить ли в верхний слайдер на главной странице |
| `invite_code` | `VARCHAR(32)` (Unique) | Уникальный код для прямой ссылки организатора |
| `min_team_size` | `SMALLINT` | Минимальный размер команды (например, $3$) |
| `max_team_size` | `SMALLINT` | Максимальный размер команды по правилам ивента (например, $5$) |
| `registration_start`| `TIMESTAMPTZ` | Дата начала регистрации |
| `registration_end` | `TIMESTAMPTZ` | Дедлайн регистрации и формирования команд |
| `event_start` | `TIMESTAMPTZ` | Начало основной части мероприятия |
| `submission_deadline`| `TIMESTAMPTZ` | Жесткий дедлайн загрузки репозитория/презентации |
| `event_end` | `TIMESTAMPTZ` | Конец мероприятия |
| `custom_fields_schema`| `JSONB` (Nullable) | Схема дополнительных вопросов анкеты под конкретный хакатон |
| `created_at` | `TIMESTAMPTZ` | Дата создания |

#### 3. Таблица `teams` (`src/models/team.py` — команды внутри события)
| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Уникальный ID команды |
| `event_id` | `UUID` (FK -> `events.id`) | К какому хакатону относится команда (`ondelete="CASCADE"`) |
| `name` | `VARCHAR(150)` | Название команды (например, `Drill Flex`) |
| `description` | `TEXT` (Nullable) | Описание идеи или кого ищет команда |
| `captain_id` | `UUID` (FK -> `users.id`) | Текущий капитан команды |
| `max_members` | `SMALLINT` | Желаемый размер команды, указанный капитаном ($\le \text{event.max\_team\_size}$) |
| `needed_roles` | `ARRAY(VARCHAR)` | Теги «Ищем» (`["фронт", "дизайн"]`) |
| `allow_auto_match` | `BOOLEAN` | Галочка «Разрешить добавлять к нам одиночек при автораспределении» (default `True`) |
| `invite_token` | `VARCHAR(64)` (Unique) | Секретный токен для прямого приглашения друзей по ссылке |
| `created_at` | `TIMESTAMPTZ` | Время создания команды |

#### 4. Таблица `event_registrations` (`src/models/event.py` — регистрации участников на событие)
*Уникальный индекс: `UniqueConstraint("event_id", "user_id", name="uq_event_user")` — один человек не может зарегистрироваться на один и тот же хакатон дважды.*

| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | ID регистрации |
| `event_id` | `UUID` (FK -> `events.id`) | ID мероприятия (`ondelete="CASCADE"`) |
| `user_id` | `UUID` (FK -> `users.id`) | ID студента (`ondelete="CASCADE"`) |
| `team_id` | `UUID` (FK -> `teams.id`, Nullable)| Если `NULL` — участник является **одиночкой** и виден в каталоге «Пригласить участников» (`ondelete="SET NULL"`) |
| `role_in_team` | `VARCHAR(100)` | Роль участника на этом хакатоне (формирует список тегов «Уже есть» у команды) |
| `custom_answers` | `JSONB` (Nullable) | Ответы на специфичные вопросы конкретного хакатона |
| `joined_team_at` | `TIMESTAMPTZ` (Nullable) | Время вступления в команду (для выбора нового капитана при выходе старого) |
| `registered_at` | `TIMESTAMPTZ` | Время регистрации на событие |

#### 5. Таблица `team_requests` (`src/models/team.py` — заявки и приглашения в команды)
| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | ID заявки/приглашения |
| `event_id` | `UUID` (FK -> `events.id`) | ID мероприятия (`ondelete="CASCADE"`) |
| `team_id` | `UUID` (FK -> `teams.id`) | В какую команду (`ondelete="CASCADE"`) |
| `user_id` | `UUID` (FK -> `users.id`) | Какой участник (`ondelete="CASCADE"`) |
| `target_role` | `VARCHAR(100)` | На какую роль подается заявка / приглашение (например, `"фронт"`) |
| `request_type` | `Enum(TeamRequestType)` | `APPLICATION` (инициатор студент) или `INVITE` (инициатор капитан) |
| `status` | `Enum(TeamRequestStatus)`| Текущий статус в пайплайне |
| `created_at` | `TIMESTAMPTZ` | Дата создания |
| `updated_at` | `TIMESTAMPTZ` | Дата последнего изменения статуса |

#### 6. Таблица `submissions` (`src/models/submission.py` — сданные проекты команд)
| Поле | Тип данных | Описание |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | ID решения |
| `event_id` | `UUID` (FK -> `events.id`) | ID мероприятия (`ondelete="CASCADE"`) |
| `team_id` | `UUID` (FK -> `teams.id`, Unique)| Одна команда сдает один итоговый сабмит (можно обновлять до дедлайна) |
| `submitted_by_user_id` | `UUID` (FK -> `users.id`) | Кто из участников команды последним загрузил или обновил решение |
| `github_url` | `VARCHAR(512)` | Ссылка на репозиторий с кодом |
| `presentation_url` | `VARCHAR(512)` (Nullable) | Ссылка на презентацию / облако |
| `demo_url` | `VARCHAR(512)` (Nullable) | Ссылка на демо-видео или развернутый прототип |
| `comment` | `TEXT` (Nullable) | Комментарий от команды для жюри |
| `submitted_at` | `TIMESTAMPTZ` | Время последней отправки |

---

## 5. Детальная бизнес-логика и обработка пограничных случаев (Edge Cases)

### 5.1. Защита от двухсторонней гонки данных (Race Condition) при вступлении в команду
Когда участник нажимает финальную кнопку «Подтвердить вступление» (переход заявки в статус `ACCEPTED`) или переходит по прямой `invite_token` ссылке, система защищает как команду от переполнения, так и участника от случайного вступления в две команды одновременно:
1. Проверяется статус мероприятия: операции разрешены строго при `event.status == EventStatus.REGISTRATION`.
2. Открывается транзакция `async with self.uow:`.
3. **Блокировка участника:** выполняется запрос регистрации участника с пессимистичной блокировкой:
   ```python
   reg_stmt = (
       select(EventRegistration)
       .where(EventRegistration.event_id == event_id, EventRegistration.user_id == user_id)
       .with_for_update()
   )
   ```
   Если `registration.team_id is not None`, выбрасывается `AlreadyInTeamError` (HTTP `409 Conflict` — «Вы уже состоите в команде»).
4. **Блокировка команды:** выполняется запрос целевой команды с пессимистичной блокировкой:
   ```python
   team_stmt = select(Team).where(Team.id == team_id).with_for_update()
   ```
5. Подсчитывается текущее число участников в `event_registrations` для данного `team_id`.
6. Лимит проверяется по `min(team.max_members, event.max_team_size)`. Если `current_members_count >= limit`, выбрасывается исключение `TeamIsFullError` (HTTP `409 Conflict`).
7. Если проверки пройдены:
   * в `event_registrations` у пользователя проставляются `team_id`, `role_in_team = request.target_role` и `joined_team_at = now()`;
   * если `target_role` присутствует в массиве `team.needed_roles`, одно вхождение этой роли удаляется из `team.needed_roles`;
   * текущая заявка переводится в `ACCEPTED`;
   * все остальные активные заявки и приглашения этого пользователя в рамках данного `event_id` массово переводятся в статус `CANCELLED`.
8. Выполняется `await self.uow.commit()`.

### 5.2. Выход из команды, управление составом и жизненный цикл хакатона
* **Ограничение по фазам хакатона:** создание команд, вступление, выход, отправка заявок и инвайтов разрешены **только** пока `event.status == EventStatus.REGISTRATION`.
* **Заморозка (`TEAM_LOCK`):** при переходе хакатона в статус `TEAM_LOCK` все незавершенные заявки в таблице `team_requests` (`PENDING_CAPTAIN`, `PENDING_USER`) автоматически переводятся в статус `CANCELLED`.
* **Выход обычного участника:** в записи `event_registrations` поле `team_id` сбрасывается в `NULL`, `joined_team_at = NULL`. Участник возвращается в список свободных одиночек.
* **Выход капитана (`user.id == team.captain_id`):**
  1. Проверяем количество оставшихся участников в команде.
  2. Если капитан был единственным участником ($1$ человек) — все связанные заявки отменяются (`CANCELLED`), команда удаляется (`DELETE`), а капитан становится одиночкой.
  3. Если в команде есть другие участники — капитанство (`team.captain_id`) автоматически передается участнику с самым ранним временем вступления (`joined_team_at`), а выходящий капитан становится одиночкой. Новому капитану отправляется уведомление в Telegram.

### 5.3. Алгоритм «умного матчинга» одиночек (`src/services/matching_services.py`)
Запускается организатором хакатона по окончании фазы регистрации:
1. **Выборка:**
   * получаем одиночек мероприятия: `registrations` где `event_id == event.id` и `team_id IS NULL`;
   * получаем неполные команды: `teams` где `allow_auto_match == True` и число участников $< \text{team.max\_members}$.
2. **Этап 1: доукомплектование существующих команд по ролям (жадный алгоритм):**
   * для каждой неполной команды с дефицитом `needed_roles` ищем подходящих одиночек по совпадению `role_in_team` и `skills`;
   * ранжируем по весу $W = | \text{team.needed\_roles} \cap (\text{user.skills} \cup \{\text{user.role\_in\_team}\}) |$;
   * добавляем лучших кандидатов в команду с обновлением `role_in_team` и удалением закрытой роли из `needed_roles`.
3. **Этап 2: формирование новых команд из оставшихся одиночек:**
   * оставшиеся одиночки группируются по ролевым корзинам (`бэк`, `фронт`, `дизайн`, `ML`, `аналитик` и т.д.);
   * алгоритм Round-Robin собирает сбалансированные команды оптимального размера $S = \lfloor \frac{\text{min\_team\_size} + \text{max\_team\_size}}{2} \rfloor$;
   * командам присваиваются названия `AutoTeam #1`, `AutoTeam #2`;
   * **назначение капитана:** капитаном новой команды автоматически назначается участник с самым ранним временем регистрации (`registered_at`) или старшим курсом;
   * **обработка неделимого остатка:** если число оставшихся одиночек $< \text{event.min\_team\_size}$, алгоритм пробует распределить их в команды с `allow_auto_match == True` (если размер не превысит `event.max_team_size`), либо оставляет их одиночками с формированием отчета для организатора с предложением ручного распределения (God Mode);
   * всем участникам автоматически приходят уведомления в Telegram со ссылками на профили сокомандников.

### 5.4. Контроль дедлайна загрузки решений (`submissions`)
* Загрузка и обновление решения (`PUT /api/v1/events/{event_id}/submission`) разрешены любому подтвержденному участнику команды (капитану или сокомандникам), пока `now() <= event.submission_deadline` и мероприятие находится в стадии `TEAM_LOCK` или `SUBMISSION`.
* Фиксируется, кто именно и когда внес последние правки.
* По истечении дедлайна возвращается `403 Forbidden` («Дедлайн загрузки решений истек»).
* Организатор данного мероприятия (`event.organizer_id == user.id`) и супер-администратор (`is_superuser`) имеют право принять или обновить работу команды после дедлайна через панель организатора.

---

## 6. Спецификация REST API (Эндпоинты FastAPI)

### 6.1. Авторизация и профиль (`src/auth/` + `src/api/user_router.py`)
* `POST /api/v1/auth/jwt/login` — вход по email и паролю (стандартный роут `fastapi-users`, форма `username` + `password`).
* `POST /api/v1/auth/jwt/logout` — выход из системы.
* `POST /api/v1/auth/register` — регистрация нового пользователя (стандартный роут `fastapi-users`, принимает `email`, `password`, `full_name`, `nickname`, `university`, `study_group`, `course`, `skills`, `primary_role`).
* `GET /api/v1/users/me` — получение своего профиля.
* `PATCH /api/v1/users/me` — редактирование профиля (`full_name`, `nickname`, `university`, `study_group`, `course`, `skills`, `primary_role`, `bio`, `vk_url`, `github_url`, `avatar_url`).
* `GET /api/v1/users/me/events` — кастомный роут: список событий, в которых участвует пользователь (для блока «Ваши события» в профиле и виджета на главной).
* `POST /api/v1/users/me/telegram-bind-link` — кастомный роут: генерация одноразовой ссылки вида `https://t.me/TeamFinderBot?start=bind_8f9a2b...` для привязки Telegram-аккаунта.

### 6.2. События и каталог (`src/api/event_router.py`)
* `GET /api/v1/events` — получение списка публичных событий для главной страницы (фильтры: `is_featured`, `status`, пагинация `limit`/`offset`).
* `GET /api/v1/events/{event_id_or_invite_code}` — детальная страница события (описание, даты, размер команды, а также `my_registration`: зарегистрирован ли текущий юзер и в какой он команде).
* `POST /api/v1/events/{event_id}/register` — регистрация участника на событие (сохранение `role_in_team` и ответов на `custom_answers`).
* `GET /api/v1/events/{event_id}/solo-participants` — каталог свободных участников без команды (`team_id IS NULL`) для экрана «Пригласить участников в команду», с фильтрацией по тегам (`skill`, `role`).

### 6.3. Команды (`src/api/team_router.py`)
* `GET /api/v1/events/{event_id}/teams` — список всех команд мероприятия (с вычисленными массивами тегов `needed_roles` [«Ищем»] и `existing_roles` [«Уже есть»], количеством участников `3/5` и списком участников с аватарками).
* `POST /api/v1/events/{event_id}/teams` — создание новой команды (`name`, `description`, `max_members`, `needed_roles`, `allow_auto_match`). Создатель автоматически становится капитаном.
* `GET /api/v1/teams/{team_id}` — детальная информация о команде (для участников внутри команды также возвращается секретный `invite_token`).
* `PATCH /api/v1/teams/{team_id}` — редактирование названия, описания, `max_members`, тегов `needed_roles` и флага `allow_auto_match` (только капитан или организатор).
* `POST /api/v1/teams/{team_id}/regenerate-token` — перевыпуск секретной ссылки-инвайта капитаном.
* `POST /api/v1/teams/join-by-token/{invite_token}` — мгновенное вступление по секретному `invite_token` (для друзей).
* `POST /api/v1/teams/{team_id}/leave` — выход из команды (с автопередачей капитанства).
* `DELETE /api/v1/teams/{team_id}/members/{user_id}` — исключение (кик) участника капитаном.

### 6.4. Пайплайн откликов и инвайтов (`src/api/request_router.py`)
* `GET /api/v1/events/{event_id}/my-requests` — список всех входящих/исходящих заявок текущего пользователя (или его команды, если он капитан) для отображения на сайте.
* `POST /api/v1/teams/{team_id}/apply` — участник жмет «Откликнуться» на карточке команды (создает `PENDING_CAPTAIN`).
* `POST /api/v1/teams/{team_id}/invite/{user_id}` — капитан жмет «Пригласить» на карточке свободного участника (создает `PENDING_USER`).
* `POST /api/v1/team-requests/{request_id}/captain-approve` — капитан одобряет отклик участника (`PENDING_CAPTAIN` $\rightarrow$ `PENDING_USER`).
* `POST /api/v1/team-requests/{request_id}/user-confirm` — финальное подтверждение вступления самим участником (`PENDING_USER` $\rightarrow$ `ACCEPTED`).
* `POST /api/v1/team-requests/{request_id}/reject` — отклонение или отмена заявки капитаном или участником (`REJECTED` / `CANCELLED`).

### 6.5. Сдача работ и панель организатора (`src/api/organizer_router.py`)
> **Контроль доступа:** все операции управления мероприятием (`PATCH`, `auto-match`, `force-assign`, `broadcast`, `export-excel`) строго проверяют владение: `event.organizer_id == current_user.id or current_user.is_superuser`. Чужие организаторы получают `403 Forbidden`.

* `PUT /api/v1/events/{event_id}/submission` — загрузка или обновление ссылок на GitHub-репозиторий, презентацию и демо до дедлайна (доступно любому участнику команды в статусах `TEAM_LOCK` / `SUBMISSION`).
* `POST /api/v1/organizer/events` — создание нового мероприятия организатором (`organizer_id` заполняется из `current_user.id`).
* `PATCH /api/v1/organizer/events/{event_id}` — изменение настроек или статуса мероприятия (`REGISTRATION` $\rightarrow$ `TEAM_LOCK` $\rightarrow$ `SUBMISSION` $\rightarrow$ `FINISHED`). При смене на `TEAM_LOCK` все висящие заявки `team_requests` отменяются (`CANCELLED`).
* `POST /api/v1/organizer/events/{event_id}/auto-match` — запуск алгоритма «умного матчинга» одиночек.
* `POST /api/v1/organizer/events/{event_id}/force-assign` — **God Mode:** принудительное перемещение любого участника в любую команду (или перевод в одиночки) организатором в обход лимитов и дедлайнов.
* `POST /api/v1/organizer/events/{event_id}/broadcast` — массовая рассылка уведомлений через Telegram-бота (фильтр: всем / только капитанам / только одиночкам).
* `GET /api/v1/organizer/events/{event_id}/export-excel` — скачивание готового `.xlsx` файла со списками команд, ФИО, учебными группами, контактами и ссылками на репозитории.

---

## 7. Спецификация Telegram-бота (`src/bot/` на Aiogram 3.x)

Бот выполняет две функции: **мгновенные интерактивные уведомления** и **рассылки от организаторов**.

### 7.1. Архитектура взаимодействия FastAPI и Aiogram
* **Отправка уведомлений из веб-сервера (FastAPI $\rightarrow$ Telegram):**
  * В бэкенде инициализируется экземпляр `aiogram.Bot(token=BOT_TOKEN)`.
  * При событиях в API (подача заявки, одобрение, вступление, кик) роутеры отправляют сообщения участникам асинхронно через `fastapi.BackgroundTasks`, чтобы не замедлять время ответа HTTP-клиенту.
* **Прием и обработка команд (Telegram $\rightarrow$ База данных):**
  * Контейнер `bot` запускает процесс `python -m src.bot.main` (Long Polling / Webhook).
  * При клике на кнопки «Одобрить» / «Подтвердить» в боте хэндлеры обращаются напрямую к сервисному слою: `TeamServices(UnitOfWork())`.
  * При ошибке или устаревании заявки (например, участник уже вступил через веб) бот выводит корректное сообщение пользователю через `callback_query.answer(text="Заявка уже неактуальна", show_alert=True)`.

### 7.2. Сценарии бота
1. **Привязка аккаунта (`/start bind_{token}`):**
   * хэндлер ловит deep-link токен, вызывает `UserServices(UnitOfWork()).bind_telegram(...)`, сохраняет `telegram_id`, `telegram_username`, ставит `is_bot_active = True`, очищает `telegram_bind_token` и отвечает: *«✅ Аккаунт успешно привязан к платформе!»*.
2. **Интерактивные карточки заявок:**
   * когда студент жмет «Откликнуться» на сайте, капитану в бот приходит сообщение с карточкой кандидата и инлайн-кнопками `[✅ Одобрить кандидата]` (`callback_data="cap_apr:{request_id}"`) и `[❌ Отклонить]` (`callback_data="req_rej:{request_id}"`);
   * нажатие кнопки в боте вызывает `TeamServices(UnitOfWork()).captain_approve_request()`, что переводит заявку в `PENDING_USER` и отправляет кандидату ответное сообщение с кнопками `[🚀 Подтвердить вступление]` (`callback_data="usr_cnf:{request_id}"`) и `[❌ Отказаться]`.
3. **Защита от блокировки при рассылках (`src/bot/sender.py`):**
   * при вызове рассылки используется асинхронный цикл с задержкой `await asyncio.sleep(0.05)` ($20$ сообщений в секунду), а каждое сообщение оборачивается в `try...except TelegramForbiddenError` (если студент заблокировал бота, ставим `is_bot_active = False` и продолжаем рассылку).

---

## 8. Инфраструктура, CORS, Docker и CI/CD

### 8.1. Настройка CORS и Cookie для фронтенда
В `src/main.py` обязательно подключается `CORSMiddleware` с явным списком доменов фронтенда (`FRONTEND_URLS` из `.env`, например `http://localhost:5173`, `http://localhost:3000`) и флагом `allow_credentials=True`.
В `.env` предусмотрена переменная `COOKIE_SECURE=False` для локальной разработки по HTTP (чтобы браузер не блокировал cookie на `localhost`) и `COOKIE_SECURE=True` для production с SSL/HTTPS.

### 8.2. Архитектура `docker-compose.yml`
Из одного `Dockerfile` (рабочая директория `/app/backend`) поднимаются два контейнера приложения, работающие с единой базой данных:
* `db`: образ `postgres:16-alpine` с volume и `healthcheck`;
* `backend`: запускает `uvicorn src.main:app --host 0.0.0.0 --port 8000`;
* `bot`: запускает `python -m src.bot.main`.

### 8.3. Пайплайн CI/CD (`.github/workflows/ci_cd.yml`)
1. **Этап `lint-and-test` (на каждый Push и Pull Request):**
   * проверка кода линтером `ruff check .` и форматом `ruff format --check .`;
   * поднятие тестового сервиса PostgreSQL в GitHub Actions, прогон миграций `alembic upgrade head` и запуск тестов `pytest`.
2. **Этап `deploy` (при слиянии в ветку `main`):**
   * подключение по SSH к серверу, `git pull`, пересборка контейнеров `docker compose up -d --build` и автоматическое применение миграций `docker compose exec -T backend alembic upgrade head`.

---

## 9. Пошаговый план для Vibe Coding (22 атомарных шага под структуру `src/`)

> **Золотое правило вайбкодинга:** никогда не проси нейросеть «написать весь бэкенд сразу» — она начнет срезать углы и оставлять комментарии `# TODO`. Положи этот файл `SPEC.md` в корень проекта, прикрепляй его через `@SPEC.md` и иди строго по этим маленьким шагам. Один шаг — один промпт!

### Фаза 1: Инфраструктура и каркас базы данных
* **Шаг 1 (зависимости, конфиг и подключение к БД):**
  > *Промпт:* «Опираясь на `@SPEC.md` (раздел 3), обнови `backend/requirements.txt` (добавь `fastapi`, `uvicorn[standard]`, `fastapi-users[sqlalchemy]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `aiogram`, `openpyxl`, `ruff`, `pytest`, `pytest-asyncio`, `httpx`), `.env`, а также `backend/src/config.py` и `backend/src/database/database.py` (`create_async_engine`, `async_session_maker`, `Base`)».
* **Шаг 2 (перечисления и доменные ошибки):**
  > *Промпт:* «По разделу 4.1 и 5 из `@SPEC.md` создай файл `backend/src/models/enums.py` со всеми `Enum` классами (наследуй их от `str, enum.Enum`) и файл `backend/src/utils/exceptions.py` с кастомными исключениями (`DomainError`, `EntityNotFoundError`, `PermissionDeniedError`, `TeamIsFullError`, `AlreadyInTeamError`, `DeadlinePassedError`, `InvalidStateError`)».
* **Шаг 3 (модель User под `fastapi-users`):**
  > *Промпт:* «По разделу 4.2 (Таблица 1) из `@SPEC.md` создай модель `backend/src/models/user.py` (удалив старый общий `models.py`). Наследуй класс `User` от `SQLAlchemyBaseUserTableUUID` и `Base` из `src.database.database`. Используй синтаксис SQLAlchemy 2.0 (`Mapped`, `mapped_column`) и тип `ARRAY(String)` из `sqlalchemy.dialects.postgresql` для поля `skills`».
* **Шаг 4 (модели Event, Team, Registration, Request, Submission):**
  > *Промпт:* «По разделу 4.2 (Таблицы 2–6) из `@SPEC.md` создай файлы `backend/src/models/event.py`, `backend/src/models/team.py`, `backend/src/models/submission.py` и экспортируй все модели в `backend/src/models/__init__.py`. Строго соблюдай внешние ключи, `UniqueConstraint` для `event_registrations` и типы `JSONB` / `ARRAY`».
* **Шаг 5 (настройка Alembic и первая миграция):**
  > *Промпт:* «Обнови `backend/src/migrations/env.py` для Alembic так, чтобы он импортировал `Base.metadata` из `src.models`. Напиши `docker-compose.yml` для локального запуска базы PostgreSQL 16 и проверь создание первой ревизии Alembic».

### Фаза 2: Базовый Репозиторий, UnitOfWork и Авторизация (`src/auth/`)
* **Шаг 6 (обновление `repository.py` и создание `uow.py`):**
  > *Промпт:* «По разделу 3.3 из `@SPEC.md` обнови `backend/src/utils/repository.py` так, чтобы `SQLAlchemyRepository` принимал `session: AsyncSession` в `__init__` и НЕ вызывал `session.commit()` внутри методов. Создай `backend/src/repositories/user_repo.py` и файл `backend/src/utils/uow.py` с классом `UnitOfWork`».
* **Шаг 7 (схемы и настройка `src/auth/` для `fastapi-users`):**
  > *Промпт:* «По разделам 4.2 и 6.1 из `@SPEC.md` обнови файлы в папке `backend/src/auth/`: в `schemas.py` реализуй `UserRead`, `UserCreate`, `UserUpdate` со всеми кастомными полями профиля; в `database.py` настрой `get_user_db` (импортируя сессию из `src.database.database`); в `manager.py` и `auth.py` настрой `UserManager`, `JWTStrategy` и объект `fastapi_users`».
* **Шаг 8 (зависимости `dependencies.py` и `UserServices`):**
  > *Промпт:* «По разделу 3.3 из `@SPEC.md` обнови `backend/src/services/user_services.py` так, чтобы конструктор `__init__(self, uow: IUnitOfWork)` принимал `uow` и сохранял его в `self.uow` (добавь метод генерации токена привязки ТГ). В `backend/src/api/dependencies.py` настрой фабрику `get_uow`, `user_service(uow = Depends(get_uow))`, а также зависимости проверки ролей `require_organizer` и `require_admin`».
* **Шаг 9 (роутер пользователей и глобальный обработчик ошибок):**
  > *Промпт:* «По разделу 6.1 из `@SPEC.md` обнови `backend/src/api/user_router.py`, создай `backend/src/api/exception_handlers.py` (маппинг доменных ошибок из `src/utils/exceptions.py` в HTTP-коды) и подключи роутеры авторизации, пользователей и `CORSMiddleware` в `backend/src/main.py`».

### Фаза 3: События, Афиша и Регистрация на хакатон
* **Шаг 10 (схемы и репозитории для Event и EventRegistration):**
  > *Промпт:* «По разделам 4.2 и 6.2 из `@SPEC.md` создай Pydantic-схемы в `backend/src/schemas/event.py` и репозитории `backend/src/repositories/event_repo.py` (поиск по `id` или `invite_code`, фильтрация публичных и `is_featured` ивентов) и `backend/src/repositories/registration_repo.py` (выборка одиночек с `team_id IS NULL` и фильтрацией по тегам). Подключи оба репозитория в `UnitOfWork` (`src/utils/uow.py`)».
* **Шаг 11 (сервис и роутер событий):**
  > *Промпт:* «По разделу 6.2 из `@SPEC.md` создай `backend/src/services/event_services.py` (с `self.uow` в `__init__`), зарегистрируй `event_service` в `src/api/dependencies.py` и создай роутер `backend/src/api/event_router.py` (каталог событий на главной, детальная страница по `id` или `invite_code`, регистрация студента на событие `POST /events/{id}/register`, каталог свободных участников `GET /events/{id}/solo-participants` и роут `GET /users/me/events`)».

### Фаза 4: Команды и теги «Ищем» / «Уже есть»
* **Шаг 12 (схемы и репозиторий команд):**
  > *Промпт:* «По разделам 2.3, 4.2 и 6.3 из `@SPEC.md` создай `backend/src/schemas/team.py` (включая вычисляемое поле `existing_roles` и список участников с аватарками) и `backend/src/repositories/team_repo.py` (включая метод `get_by_id_for_update` с `.with_for_update()` для защиты от Race Condition). Подключи его в `UnitOfWork`».
* **Шаг 13 (сервис управления командой: создание, инвайт-токен, выход, кик):**
  > *Промпт:* «По разделам 5.1, 5.2 и 6.3 из `@SPEC.md` создай `backend/src/services/team_services.py` (с `self.uow` в `__init__`). Реализуй методы создания команды, редактирования, вступления по прямому `invite_token` (с блокировкой строки команды), исключения участника капитаном и выхода из команды (`leave_team`) с автоматической передачей капитанства старейшему участнику или удалением пустой команды».
* **Шаг 14 (роутер команд):**
  > *Промпт:* «По разделу 6.3 из `@SPEC.md` добавь фабрику `team_service` в `src/api/dependencies.py`, создай роутер `backend/src/api/team_router.py` и подключи его в `src/main.py`».

### Фаза 5: Пайплайн заявок и приглашений (Двойное подтверждение)
* **Шаг 15 (репозиторий и логика `team_requests`):**
  > *Промпт:* «По разделам 2.4, 5.1 и 6.4 из `@SPEC.md` создай `backend/src/repositories/request_repo.py` (включая метод массовой отмены остальных активных заявок пользователя `cancel_other_user_requests`) и добавь его в `UnitOfWork`. Допиши в `backend/src/services/team_services.py` методы: `apply_to_team`, `invite_user_to_team`, `captain_approve_request`, `user_confirm_request` (с `with_for_update()` и удалением закрытой роли из `needed_roles`) и `reject_request`».
* **Шаг 16 (роутер заявок и инвайтов):**
  > *Промпт:* «По разделу 6.4 из `@SPEC.md` создай роутер `backend/src/api/request_router.py` (включая `GET /events/{event_id}/my-requests`) и подключи его в `src/main.py`».

### Фаза 6: Telegram-бот (`src/bot/` на Aiogram 3.x) и уведомления
* **Шаг 17 (рассыльщик и привязка аккаунта через `/start`):**
  > *Промпт:* «По разделу 7 из `@SPEC.md` создай `backend/src/bot/sender.py` (безопасная отправка сообщений с троттлингом `0.05s` и перехватом `TelegramForbiddenError`), `backend/src/bot/keyboards/inline.py` и хэндлер `backend/src/bot/handlers/start.py` для привязки аккаунта по токену `/start bind_{token}` через вызов `UserServices(UnitOfWork())`».
* **Шаг 18 (интерактивные кнопки одобрения и подтверждения в боте):**
  > *Промпт:* «По разделу 7 из `@SPEC.md` создай `backend/src/bot/handlers/requests.py` для обработки нажатий инлайн-кнопок капитаном (`cap_apr`, `req_rej`) и участником (`usr_cnf`, `req_rej`) через вызов `TeamServices(UnitOfWork())`. Собери точку входа `backend/src/bot/main.py` и добавь отправку уведомлений через `BackgroundTasks` в роутерах заявок».

### Фаза 7: Суперсилы организатора (Умный матчинг, Репозитории, Excel)
* **Шаг 19 (алгоритм «умного матчинга» одиночек):**
  > *Промпт:* «По разделу 5.3 из `@SPEC.md` реализуй `backend/src/services/matching_services.py` (с `self.uow` в `__init__`). Напиши жадный алгоритм доукомплектования существующих команд с `allow_auto_match=True` по пересечению `needed_roles` и `skills`, а затем формирование новых сбалансированных команд (`AutoTeam #N`) по принципу Round-Robin из оставшихся одиночек».
* **Шаг 20 (сдача проектов с дедлайном и экспорт в Excel):**
  > *Промпт:* «По разделам 5.4 и 6.5 из `@SPEC.md` создай `backend/src/schemas/submission.py`, `backend/src/repositories/submission_repo.py` (добавь в `UnitOfWork`) и `backend/src/services/export_services.py` (генерация красивого `.xlsx` файла через `openpyxl` со столбцами: Команда, Капитан, ФИО участника, Роль, Вуз, Группа, Курс, Telegram, Email, Ссылка на GitHub, Презентация)».
* **Шаг 21 (панель организатора и God Mode):**
  > *Промпт:* «По разделу 6.5 из `@SPEC.md` создай роутер `backend/src/api/organizer_router.py` (защищенный зависимостью `require_organizer`): создание/редактирование события, запуск `auto-match`, ручное перемещение участника `force-assign`, массовая рассылка в ТГ `broadcast` и скачивание Excel-отчета `StreamingResponse`».
* **Шаг 22 (Docker, тесты и CI/CD):**
  > *Промпт:* «По разделу 8 из `@SPEC.md` создай финальный `Dockerfile`, полный `docker-compose.yml` (сервисы `db`, `backend`, `bot`), пайплайн `.github/workflows/ci_cd.yml` и интеграционные тесты в `backend/tests/` для проверки пайплайна заявок и умного матчинга».