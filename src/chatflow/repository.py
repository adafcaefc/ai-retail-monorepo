from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

def list_conversations(
    session,
):
    result = session.execute(
        text("""
            SELECT
                id,
                title,
                created_at
            FROM chat.conversations
            ORDER BY created_at DESC
        """)
    )

    return [
        dict(row._mapping)
        for row in result
    ]

def create_conversation(
    session: Session,
    title: str,
) -> str:
    conversation_id = str(uuid4())

    session.execute(
        text("""
            INSERT INTO chat.conversations (
                id,
                title
            )
            VALUES (
                :id,
                :title
            )
        """),
        {
            "id": conversation_id,
            "title": title,
        },
    )

    session.commit()

    return conversation_id


def save_message(
    session: Session,
    conversation_id: str,
    sender: str,
    channel: str,
    message: str,
) -> str:
    message_id = str(uuid4())

    session.execute(
        text("""
            INSERT INTO chat.messages (
                id,
                conversation_id,
                sender,
                channel,
                message
            )
            VALUES (
                :id,
                :conversation_id,
                :sender,
                :channel,
                :message
            )
        """),
        {
            "id": message_id,
            "conversation_id": conversation_id,
            "sender": sender,
            "channel": channel,
            "message": message,
        },
    )

    session.commit()

    return message_id


def get_messages(
    session: Session,
    conversation_id: str,
):
    result = session.execute(
        text("""
            SELECT
                sender,
                channel,
                message,
                created_at
            FROM chat.messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at ASC
        """),
        {
            "conversation_id": conversation_id,
        },
    )

    return [
        dict(row._mapping)
        for row in result
    ]

def get_conversation_messages(
    session,
    conversation_id,
):
    result = session.execute(
        text("""
            SELECT
                sender,
                channel,
                message,
                created_at
            FROM chat.messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at
        """),
        {
            "conversation_id": conversation_id
        }
    )

    return [
        dict(row._mapping)
        for row in result
    ]