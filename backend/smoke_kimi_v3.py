from __future__ import annotations

import asyncio

from app.compilers.procedural import request_fingerprint
from app.config import get_settings
from app.domain.v3_validator import SceneV3Validator
from app.providers.base import ProviderError
from app.providers.kimi import KimiProvider
from app.services.v3.capability_registry import CapabilityRegistry
from app.services.v3.fidelity import SemanticFidelityEvaluator
from app.services.v3.intent_compiler import SceneIntentCompiler
from app.services.v3.layout_solver import LayoutSolver
from app.services.v3.recipe_compiler import VisualRecipeCompiler


PROMPT = (
    "在浩瀚宇宙中，前方是一颗耀眼恒星，旁边是一颗脉冲星，"
    "远处有一个黑洞，远处群星点点。"
)
PREFERENCES = {
    "styleKit": "auto",
    "time": "auto",
    "weather": "auto",
    "density": 0.68,
    "quality": "balanced",
    "scale": "compact",
    "seed": None,
}


async def main() -> None:
    provider = KimiProvider(get_settings())
    compiler = SceneIntentCompiler(provider, max_repairs=0)
    try:
        result = await compiler.compile(PROMPT, PREFERENCES)
    except ProviderError as exc:
        print(f"Kimi V3 smoke test failed: {exc.code}")
        if exc.debug_detail:
            print(exc.debug_detail)
        raise SystemExit(1) from exc

    registry = CapabilityRegistry()
    resolutions = registry.resolve_all(result.intent)
    layout = LayoutSolver().solve(result.intent)
    scene = VisualRecipeCompiler().compile(
        result.intent,
        resolutions,
        layout,
        fingerprint=request_fingerprint(PROMPT, PREFERENCES),
        version_kind="final",
        quality=PREFERENCES["quality"],
    )
    fidelity = SemanticFidelityEvaluator().evaluate(
        result.intent, scene, resolutions, layout
    )
    SceneV3Validator().validate(scene, result.intent)
    if not fidelity.passed:
        raise SystemExit("Kimi V3 smoke test failed: fidelity gate rejected the scene")

    labels = ", ".join(item["label"] for item in resolutions)
    print(
        f"Kimi V3 smoke test passed: {result.intent['title']} "
        f"({result.intent['sceneMode']}, {fidelity.report['requiredCoverage']:.0%} coverage)"
    )
    print(f"Resolved entities: {labels}")


if __name__ == "__main__":
    asyncio.run(main())
