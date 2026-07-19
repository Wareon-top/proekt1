from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from wareon.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Sale(Base):
    """Одна продажа: выручка, себестоимость, источник трафика."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    revenue: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class TrackedChat(Base):
    """Канал или группа, куда добавлен бот для аналитики."""

    __tablename__ = "tracked_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_type: Mapped[str] = mapped_column(String(32))
    added_by_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatEvent(Base):
    """Событие в отслеживаемом чате: сообщение, вступление, выход."""

    __tablename__ = "chat_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # message | join | leave | post
    actor_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class TableUpload(Base):
    """Загруженная пользователем «умная таблица» и её краткое описание."""

    __tablename__ = "table_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReportSubscription(Base):
    """Подписка на регулярный отчёт: ежедневный или еженедельный."""

    __tablename__ = "report_subscriptions"
    __table_args__ = (UniqueConstraint("user_tg_id", "kind", name="uq_sub_user_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # daily | weekly
    hour: Mapped[int] = mapped_column(Integer)  # время по МСК
    minute: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiBrief(Base):
    """Кэш ежедневной ИИ-сводки: одна на пользователя в сутки — экономит токены."""

    __tablename__ = "ai_briefs"
    __table_args__ = (UniqueConstraint("user_tg_id", "day", name="uq_brief_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD (UTC)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CustomMetric(Base):
    """Кастомная метрика клиента: формула из «кирпичиков» над данными.

    Формула — безопасное арифметическое выражение над базовыми переменными
    (revenue, cost, orders, ...), проверяется движком формул. Может завести как
    человек, так и ИИ-ассистент (created_by)."""

    __tablename__ = "custom_metrics"
    __table_args__ = (UniqueConstraint("user_tg_id", "key", name="uq_metric_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    key: Mapped[str] = mapped_column(String(48))  # машинный идентификатор
    title: Mapped[str] = mapped_column(String(128))
    expression: Mapped[str] = mapped_column(String(256))
    unit: Mapped[str] = mapped_column(String(16), default="")
    direction: Mapped[str] = mapped_column(String(8), default="up")  # up | down | neutral
    area: Mapped[str] = mapped_column(String(24), default="custom")
    created_by: Mapped[str] = mapped_column(String(8), default="user")  # user | ai
    # Метрика, предложенная ИИ, но ещё не подтверждённая (при неполной автономии).
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentSetting(Base):
    """Уровень автономии ИИ-оркестратора для клиента (Раздел 2 «Управляемо»)."""

    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # autopilot — делает сам; semi — рутину сам, наружу с подтверждением;
    # manual — только предлагает.
    level: Mapped[str] = mapped_column(String(16), default="semi")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AlertSetting(Base):
    """Порог алерта по марже: предупреждаем, когда маржа за сутки ниже порога."""

    __tablename__ = "alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    margin_threshold_pct: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
