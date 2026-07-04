import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview


def main():
    fixture = ROOT / "test_data" / "paint_studio_source_renderer_fixture.json"
    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "source_renderer_fixture.png"
        metadata = render_paint_studio_preview(str(fixture), str(output), ssaa=2)

        assert output.exists(), "Renderer did not create an output PNG."
        assert metadata["canvas"]["width"] == 160
        assert metadata["canvas"]["height"] == 120
        assert metadata["total_shapes"] == 5
        assert metadata["rendered_shape_count"] == 4
        assert metadata["skipped_shape_count"] == 1
        assert metadata["unsupported_shape_types"] == {}

    print("Paint Studio source renderer fixture smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
