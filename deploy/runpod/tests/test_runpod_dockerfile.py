"""The RunPod image layer ships every file the runtime imports."""
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_tools_is_a_regular_package_in_the_image():
    # Without tools/__init__.py, any installed package named "tools" would
    # shadow the Sarvam proxy (a regular package beats a namespace package).
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY tools/__init__.py /app/tools/__init__.py" in text
    assert text.index("COPY tools/__init__.py") < text.index('import tools.sarvam_asr_proxy.app')
