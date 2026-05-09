"""SQLAlchemy declarative models for session storage."""

import datetime
from typing import Any

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float, Index
from sqlalchemy.orm import relationship

from agent_evolver.storage.db import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    agent_id = Column(String(128), nullable=True)
    user_id = Column(String(128), nullable=True)
    task_desc = Column(Text, nullable=True)
    status = Column(String(32), default="in_progress")  # in_progress | completed | failed
    total_tokens = Column(Integer, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    tool_calls = relationship("ToolCall", back_populates="session", cascade="all, delete-orphan")
    skill_invocations = relationship(
        "SkillInvocation", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # system | user | assistant | tool
    content = Column(Text, nullable=True)
    tokens = Column(Integer, nullable=True)
    ts = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    session = relationship("Session", back_populates="messages")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), nullable=False, index=True)
    tool_name = Column(String(256), nullable=False)
    args = Column(JSON, nullable=True)
    result = Column(Text, nullable=True)
    status = Column(String(32), default="unknown")  # success | error | unknown
    ts = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    session = relationship("Session", back_populates="tool_calls")


class SkillInvocation(Base):
    __tablename__ = "skill_invocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), nullable=False, index=True)
    skill_name = Column(String(256), nullable=False)
    applied = Column(Integer, default=0)  # 0 or 1
    fallback_to = Column(String(256), nullable=True)
    ts = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    session = relationship("Session", back_populates="skill_invocations")


class PatternOccurrence(Base):
    """Records of discovered patterns across sessions for statistical validation."""

    __tablename__ = "pattern_occurrences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_hash = Column(String(64), nullable=False, index=True)
    pattern_type = Column(String(32), nullable=False)
    session_id = Column(String(256), ForeignKey("sessions.id"), nullable=False)
    similarity_score = Column(Float, nullable=False)
    first_seen_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    captured_as_skill = Column(String(512), nullable=True)

    __table_args__ = (
        Index("idx_pattern_hash_type", "pattern_hash", "pattern_type"),
    )
