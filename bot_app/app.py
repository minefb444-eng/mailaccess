from __future__ import annotations

import logging

import telebot

from .api_client import WorkerApiClient
from .config import BotConfig
from .handlers import BotHandlers
from .polling import PollingManager
from .services import MailAccessService
from .state import BotState

LOGGER = logging.getLogger(__name__)


class MailAccessBotApp:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.bot = telebot.TeleBot(config.bot_token, parse_mode="HTML")
        self.state = BotState(config.session_file)
        self.api_client = WorkerApiClient(
            base_url=config.worker_url,
            bot_secret=config.bot_secret,
            timeout_seconds=config.request_timeout_seconds,
        )
        self.service = MailAccessService(
            state=self.state,
            api_client=self.api_client,
            worker_url=config.worker_url,
            sync_state_each_call=False,
        )
        self.polling_manager = PollingManager(
            bot=self.bot,
            config=config,
            state=self.state,
            api_client=self.api_client,
            log_activity=self.log_activity,
        )
        self.handlers = BotHandlers(
            bot=self.bot,
            config=self.config,
            state=self.state,
            api_client=self.api_client,
            polling_manager=self.polling_manager,
            service=self.service,
        )

    def initialize(self) -> None:
        self.state.load_sessions()
        LOGGER.info("Loaded sessions for %s users", len(self.state.list_user_ids()))
        self.polling_manager.restore_threads()

    def run(self) -> None:
        self.initialize()
        LOGGER.info("Starting Telegram polling loop...")
        self.bot.polling(none_stop=True, interval=0, timeout=20)

    def log_activity(self, text: str) -> None:
        if not self.config.log_channel_id:
            return
        try:
            self.bot.send_message(self.config.log_channel_id, text)
        except Exception as exc:
            LOGGER.warning("Failed sending activity log: %s", exc)
