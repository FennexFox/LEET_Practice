from __future__ import annotations

import builtins
from types import SimpleNamespace

from leet_practice.compare_ocr_engines import paddle_option_metadata, resolve_paddle_options


def test_resolve_paddle_options_applies_supported_constructor_options() -> None:
    args = SimpleNamespace(
        paddle_lang="korean",
        paddle_device="gpu:0",
        paddle_cpu_threads=8,
        paddle_text_recognition_batch_size=64,
        paddle_text_det_limit_side_len=3584,
        paddle_disable_mkldnn=True,
        paddle_disable_pir=True,
        paddle_disable_doc_preprocess=True,
        paddle_preimport_torch=True,
        paddle_preimport_paddle=False,
    )

    effective, support = resolve_paddle_options(
        args,
        {
            "device": object(),
            "cpu_threads": object(),
            "text_recognition_batch_size": object(),
            "text_det_limit_side_len": object(),
        },
    )

    assert support["paddle_device"] is True
    assert support["paddle_text_recognition_batch_size"] is True
    assert support["paddle_text_det_limit_side_len"] is True
    assert effective["paddle_device"] == "gpu:0"
    assert effective["paddle_text_recognition_batch_size"] == 64
    assert effective["paddle_text_det_limit_side_len"] == 3584


def test_resolve_paddle_options_drops_unsupported_constructor_options() -> None:
    args = SimpleNamespace(
        paddle_lang="korean",
        paddle_device="gpu:0",
        paddle_cpu_threads=8,
        paddle_text_recognition_batch_size=64,
        paddle_text_det_limit_side_len=3584,
        paddle_disable_mkldnn=True,
        paddle_disable_pir=True,
        paddle_disable_doc_preprocess=True,
        paddle_preimport_torch=True,
        paddle_preimport_paddle=False,
    )

    effective, support = resolve_paddle_options(args, {})

    assert support["paddle_device"] is False
    assert support["paddle_text_recognition_batch_size"] is False
    assert support["paddle_text_det_limit_side_len"] is False
    assert effective["paddle_device"] is None
    assert effective["paddle_cpu_threads"] is None
    assert effective["paddle_text_recognition_batch_size"] is None
    assert effective["paddle_text_det_limit_side_len"] is None


def test_paddle_option_metadata_marks_effective_options_unsupported_when_import_fails(monkeypatch) -> None:
    args = SimpleNamespace(
        paddle_lang="korean",
        paddle_device="gpu:0",
        paddle_cpu_threads=8,
        paddle_text_recognition_batch_size=64,
        paddle_text_det_limit_side_len=3584,
        paddle_disable_mkldnn=True,
        paddle_disable_pir=True,
        paddle_disable_doc_preprocess=True,
        paddle_preimport_torch=True,
        paddle_preimport_paddle=False,
    )
    original_import = builtins.__import__

    def fake_import(name, *args_, **kwargs):
        if name == "paddleocr":
            raise ImportError(name)
        return original_import(name, *args_, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    metadata = paddle_option_metadata(args)

    assert metadata["requested_options"]["paddle_device"] == "gpu:0"
    assert metadata["requested_options"]["paddle_text_recognition_batch_size"] == 64
    assert metadata["requested_options"]["paddle_text_det_limit_side_len"] == 3584
    assert metadata["effective_options"]["paddle_device"] is None
    assert metadata["effective_options"]["paddle_cpu_threads"] is None
    assert metadata["effective_options"]["paddle_text_recognition_batch_size"] is None
    assert metadata["effective_options"]["paddle_text_det_limit_side_len"] is None
    assert metadata["option_support"]["paddle_text_recognition_batch_size"] is False
    assert metadata["option_support"]["paddle_text_det_limit_side_len"] is False
