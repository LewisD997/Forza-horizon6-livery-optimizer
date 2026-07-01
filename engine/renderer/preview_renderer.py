def render_preview_placeholder(layers, image_info):
    return {
        "status": "placeholder",
        "message": "Renderer module exists, but image preview rendering is not implemented in the MVP.",
        "layer_count": len(layers),
        "target_size": image_info.get("size"),
    }
