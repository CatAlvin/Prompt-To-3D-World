from __future__ import annotations

import asyncio

from app.config import get_settings
from app.domain.scene_validator import SceneValidator
from app.providers.base import ProviderError
from app.providers.kimi import KimiProvider
from app.services.prompt_compiler import PromptCompiler


async def main() -> None:
    provider = KimiProvider(get_settings())
    compiler = PromptCompiler(provider, SceneValidator(), max_repairs=0)
    try:
        result = await compiler.compile(
            "A small cyberpunk Japanese alley at night with ramen shops and neon signs."
        )
    except ProviderError as exc:
        print(f"Kimi smoke test failed: {exc.code}")
        if exc.debug_detail:
            print(exc.debug_detail)
        raise SystemExit(1) from exc
    else:
        print(
            f"Kimi smoke test passed: {result.scene_json['title']} "
            f"({len(result.scene_json['nodes'])} nodes)"
        )


if __name__ == "__main__":
    asyncio.run(main())
