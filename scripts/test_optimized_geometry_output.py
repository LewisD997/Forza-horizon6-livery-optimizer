import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.geometry_optimizer import optimize_geometry_noop
from engine.output.optimized_geometry_writer import (
    OptimizedGeometryWriteError,
    write_optimized_geometry,
)


def main():
    fixture = ROOT / "test_data" / "paint_studio_source_renderer_fixture.json"
    original_text = fixture.read_text(encoding="utf-8")
    geometry = json.loads(original_text)
    result = optimize_geometry_noop(geometry)
    assert result["report"]["input_shape_count"] == len(geometry["shapes"])
    assert result["report"]["output_shape_count"] == len(geometry["shapes"])
    assert result["report"]["changed_shape_count"] == 0

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "optimized_geometry.json"
        report = write_optimized_geometry(
            str(fixture),
            str(output),
            shapes=result["geometry"]["shapes"],
            metadata={"optimizer_report": result["report"], "renderer_used": "test"},
        )
        assert output.exists()
        assert output.with_name("optimized_geometry_optimization_report.json").exists()
        optimized = json.loads(output.read_text(encoding="utf-8"))
        assert len(optimized["shapes"]) == len(geometry["shapes"])
        assert fixture.read_text(encoding="utf-8") == original_text
        assert report["optimization_mode"] == "noop"
        assert report["safety_level"] == "safe"

        try:
            write_optimized_geometry(str(fixture), str(output), shapes=result["geometry"]["shapes"])
            raise AssertionError("Expected overwrite protection to reject existing output.")
        except OptimizedGeometryWriteError:
            pass

        try:
            write_optimized_geometry(str(fixture), str(fixture), shapes=result["geometry"]["shapes"])
            raise AssertionError("Expected input overwrite protection to reject same path.")
        except OptimizedGeometryWriteError:
            pass

    print("Optimized geometry output smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
