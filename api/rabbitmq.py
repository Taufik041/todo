import json
import logging
import os
from typing import Any

import aio_pika

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
EXCHANGE_NAME = "todos"

logger = logging.getLogger(__name__)

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None


async def _get_exchange() -> aio_pika.abc.AbstractExchange | None:
    global _connection, _channel, _exchange
    try:
        if _connection is None or _connection.is_closed:
            _connection = await aio_pika.connect_robust(RABBITMQ_URL)
        if _channel is None or _channel.is_closed:
            _channel = await _connection.channel()
        if _exchange is None:
            _exchange = await _channel.declare_exchange(
                EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
            )
        return _exchange
    except Exception as exc:
        logger.warning("RabbitMQ unavailable, skipping event publish: %s", exc)
        _connection = None
        _channel = None
        _exchange = None
        return None


async def publish_event(event_type: str, data: dict[str, Any]) -> None:
    exchange = await _get_exchange()
    if exchange is None:
        return
    try:
        payload = json.dumps({"event_type": event_type, "data": data}, default=str)
        await exchange.publish(
            aio_pika.Message(
                body=payload.encode(),
                content_type="application/json",
            ),
            routing_key=event_type,
        )
    except Exception as exc:
        logger.warning("Failed to publish event %s: %s", event_type, exc)


async def close() -> None:
    global _connection, _channel, _exchange
    _exchange = None
    if _channel and not _channel.is_closed:
        await _channel.close()
    if _connection and not _connection.is_closed:
        await _connection.close()
    _channel = None
    _connection = None
