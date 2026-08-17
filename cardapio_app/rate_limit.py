"""
Rate limiting mínimo para endpoints públicos (Fase 1 do pagamento online).

RESSALVA TÉCNICA OBRIGATÓRIA (decisão do plano da Fase 1):

    Este contador é EM MEMÓRIA e POR PROCESSO. Se o Cardápio passar a rodar com
    múltiplas instâncias ou múltiplos workers, cada processo terá seu próprio
    contador e o limite deixa de ser global.

    Para o MVP isso é aceitável: o objetivo é evitar que um cliente dispare
    dezenas de criações de cobrança em sequência, não construir uma defesa
    contra ataque distribuído.

    Rate limiting distribuído (Redis) é escopo de fase posterior.

O módulo é puro: não importa Flask nem pg_store, para permitir teste isolado.
"""

from __future__ import annotations

import threading
import time
from typing import Final

#: Janela padrão de contagem, em segundos.
DEFAULT_WINDOW_SECONDS: Final[int] = 60

#: Teto de chaves distintas mantidas em memória. Evita crescimento indefinido
#: quando o atacante varia a chave (ex.: IP falsificado por requisição).
MAX_TRACKED_KEYS: Final[int] = 20_000

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def _prune_locked(*, now: float, window: int) -> None:
    """Remove chaves sem batidas dentro da janela. Requer _lock adquirido."""
    cutoff = now - window
    for key in [k for k, ts in _hits.items() if not ts or ts[-1] < cutoff]:
        _hits.pop(key, None)


def check(*, key: str, limit: int, window: int = DEFAULT_WINDOW_SECONDS) -> tuple[bool, int]:
    """Registra uma batida e informa se ela é permitida.

    Retorna (permitido, retry_after_segundos). Quando permitido, retry_after é 0.

    A batida só é registrada quando permitida: requisições bloqueadas não
    estendem a punição, o que evita que um cliente fique preso indefinidamente
    por continuar tentando.
    """
    k = str(key or "").strip()
    if not k or limit <= 0:
        return True, 0

    now = time.monotonic()
    cutoff = now - window

    with _lock:
        timestamps = [t for t in _hits.get(k, []) if t > cutoff]

        if len(timestamps) >= limit:
            _hits[k] = timestamps
            retry_after = max(1, int(window - (now - timestamps[0])) + 1)
            return False, retry_after

        timestamps.append(now)
        _hits[k] = timestamps

        if len(_hits) > MAX_TRACKED_KEYS:
            _prune_locked(now=now, window=window)

        return True, 0


def reset() -> None:
    """Limpa todos os contadores. Uso exclusivo de teste."""
    with _lock:
        _hits.clear()
