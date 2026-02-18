from bot_app.formatting import extract_otp, format_time, parse_email_preview, safe_shorten, sanitize, shorten


def test_extract_otp_matches_6_digits() -> None:
    assert extract_otp("Your login code is 193827 and expires soon.") == "193827"


def test_extract_otp_returns_none_when_absent() -> None:
    assert extract_otp("No OTP here.") is None


def test_format_time_handles_invalid_input() -> None:
    assert format_time("abc") == ""


def test_parse_email_preview_plain_text_message() -> None:
    raw = "Subject: Test\nContent-Type: text/plain; charset=utf-8\n\nHello world!"
    assert parse_email_preview(raw) == "Hello world!"


def test_sanitize_escapes_html() -> None:
    assert sanitize("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"


def test_shorten_truncates() -> None:
    assert shorten("abcdef", 4) == "abc…"


def test_safe_shorten_avoids_broken_html_entities() -> None:
    assert safe_shorten("<tag>", 2) == "&lt;…"
