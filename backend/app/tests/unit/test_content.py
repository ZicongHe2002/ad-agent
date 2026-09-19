from app.services.content_service import normalize_content


def test_normalize_content_is_stable() -> None:
    first = normalize_content(
        {
            "title": "  羊绒  穿搭 ",
            "caption": "奶油白大衣",
            "hashtags": ["#秋冬", "秋冬"],
        }
    )
    second = normalize_content(
        {
            "title": "羊绒 穿搭",
            "caption": "奶油白大衣",
            "hashtags": ["秋冬"],
        }
    )
    assert first.content_hash == second.content_hash
    assert first.hashtags == ["秋冬"]
