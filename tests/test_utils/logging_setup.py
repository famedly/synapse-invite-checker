# Copyright 2019 New Vector Ltd
# SPDX-FileCopyrightText: 2026 Famedly GmbH
#
# SPDX-License-Identifier: Apache-2.0
import logging
import os

import twisted.logger
from synapse.logging.context import LoggingContextFilter
from synapse.synapse_rust import reset_logging_config


class ToTwistedHandler(logging.Handler):
    """logging handler which sends the logs to the twisted log"""

    tx_log = twisted.logger.Logger()

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        log_level = record.levelname.lower().replace("warning", "warn")
        self.tx_log.emit(
            twisted.logger.LogLevel.levelWithName(log_level), "{entry}", entry=log_entry
        )


def setup_logging() -> None:
    """Configure the python logging appropriately for the tests.

    (Logs will end up in _trial_temp.)
    """
    root_logger = logging.getLogger()

    # We exclude `%(asctime)s` from this format because the Twisted logger adds its own
    # timestamp
    log_format = "%(name)s - %(lineno)d - " "%(levelname)s - %(request)s - %(message)s"

    handler = ToTwistedHandler()
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    handler.addFilter(LoggingContextFilter())
    root_logger.addHandler(handler)

    log_level = os.environ.get("SYNAPSE_TEST_LOG_LEVEL", "DEBUG")
    root_logger.setLevel(log_level)

    # In order to not add noise by default (since we only log ERROR messages for trial
    # tests as configured above), we only enable this for developers for looking for
    # more INFO or DEBUG.
    if root_logger.isEnabledFor(logging.INFO):
        # Log when events are (maybe unexpectedly) filtered out of responses in tests. It's
        # just nice to be able to look at the CI log and figure out why an event isn't being
        # returned.
        logging.getLogger("synapse.visibility.filtered_event_debug").setLevel(
            logging.DEBUG
        )

    # Blow away the pyo3-log cache so that it reloads the configuration.
    reset_logging_config()
