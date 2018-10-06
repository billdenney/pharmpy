
from pharmpy import Model


def test_model_denovo():
    """Create agnostic :class:`~pharmpy.generic.Model` object,  *de novo* (no file)."""
    empty = Model()
    assert not empty.source.on_disk
    assert empty.path is None
    assert empty.content is None