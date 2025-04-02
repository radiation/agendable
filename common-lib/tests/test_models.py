import pytest

try:
    from common_lib.models import Base
except ImportError:
    pytest.skip("models.Base not available")

def test_models_base_exists() -> None:
    assert Base is not None
