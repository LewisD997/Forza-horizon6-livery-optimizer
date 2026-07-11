def generate_semantic_region_proposal(image_path, options=None):
    options = options or {}; backend = options.get("backend", "auto")
    if backend in {"auto", "heuristic-anime", "heuristic_anime_v1"}:
        from .heuristic_anime_backend import generate_heuristic_anime_proposal
        return generate_heuristic_anime_proposal(image_path, options)
    raise ValueError(f"Unsupported semantic region backend: {backend}")
