from __future__ import annotations

from types import SimpleNamespace

from leet_practice.compare_ocr_engines import resolve_paddle_options


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
