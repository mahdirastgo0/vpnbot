from app.config import settings
from app.services.sanaei_client import SanaeiClient

_clients: dict[str, SanaeiClient] = {}


def get_client(panel_key: str) -> SanaeiClient:
    if panel_key not in _clients:
        panel = settings.PANELS[panel_key]
        _clients[panel_key] = SanaeiClient(panel)
    return _clients[panel_key]


async def close_all() -> None:
    for client in _clients.values():
        await client.close()
    _clients.clear()
