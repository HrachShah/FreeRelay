from freerelay.shared.security.pii import detect_pii, mask_pii, unmask_pii


def test_mask_pii_prefers_longest_overlapping_detection() -> None:
    text = "Contact 123-45-6789@example.com"

    result = mask_pii(text)

    assert result.masked_text == "Contact [EMAIL_1]"
    assert result.replacement_map == {"[EMAIL_1]": "123-45-6789@example.com"}
    assert unmask_pii(result.masked_text, result.replacement_map) == text


def test_mask_pii_skips_overlapping_custom_detections() -> None:
    text = "secret@example.com"
    detections = detect_pii(text)

    result = mask_pii(text, detections + detections)

    assert result.masked_text == "[EMAIL_1]"
    assert len(result.detections) == 1
