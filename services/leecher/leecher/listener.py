import sys
import time
import signal
import logging
from typing import Any, Callable, Union

import ftrack_api
import ayon_api

IGNORE_TOPICS = {
    "ftrack.meta.connected",
    "ftrack.meta.disconnected",
}

log = logging.getLogger(__name__)


def create_event_description(payload: dict[str, Any]):
    uname = payload.get("source", {}).get("user", {}).get("username")
    if not uname:
        return f"Leeched {payload['topic']}"
    return f"Leeched {payload['topic']} by {uname}"


def callback(event):
    if event["topic"] in IGNORE_TOPICS:
        return

    event_data = event._data
    description = create_event_description(event_data)

    ayon_api.dispatch_event(
        "ftrack.leech",
        sender=ayon_api.ServiceContext.service_name,
        event_hash=event_data["id"],
        description=description,
        payload=event_data,
    )
    log.info(f"Stored event {event_data['topic']}")


def listen_loop(session, callback):
    while not session.event_hub.connected:
        time.sleep(0.1)

    session.event_hub.subscribe("topic=*", callback)
    session.event_hub.wait()


def main(func: Union[Callable, None] = None):
    logging.basicConfig()
    log.setLevel(logging.DEBUG)

    log.info("Starting listener")
    if func is None:
        func = callback

    ayon_api.init_service()
    settings = ayon_api.get_service_addon_settings()

    log.debug("Creating ftrack session")
    session = ftrack_api.Session(
        settings["ftrack_server"],
        settings["service_settings"]["api_key"],
        settings["service_settings"]["username"],
        auto_connect_event_hub=True,
    )

    # Register interrupt signal
    def signal_handler(sig, frame):
        log.warning("Process stop requested. Terminating process.")
        if session.event_hub.connected is True:
            session.event_hub.disconnect()
        session.close()
        log.warning("Termination finished.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log.info("Main loop starting")
    sys.exit(listen_loop(session, func))
    log.info("Process stopped")
