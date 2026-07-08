import asyncio
import json
import logging
import os

import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = "todos"
QUEUE_NAME = "todo_worker"


async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body)
            event_type = payload.get("event_type", message.routing_key)
            data = payload.get("data", {})
            logger.info(
                "Event received | type=%s | payload=%s", event_type, json.dumps(data)
            )
        except Exception as exc:
            logger.error("Failed to process message: %s", exc)


async def main() -> None:
    delay = 1
    while True:
        try:
            logger.info("Connecting to RabbitMQ at %s", RABBITMQ_URL)
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(
                    EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
                )
                queue = await channel.declare_queue(QUEUE_NAME, durable=True)
                await queue.bind(exchange, routing_key="todo.*")

                logger.info("Worker ready, waiting for events...")
                delay = 1  # reset backoff on successful connect
                await queue.consume(on_message)
                await asyncio.Future()  # run forever
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(
                "RabbitMQ connection error: %s. Retrying in %ds...", exc, delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
