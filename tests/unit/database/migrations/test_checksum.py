from ape_sdk.database.migrations.checksum import calculate_sha256


def test_checksum_is_stable_for_same_file_content(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "001.sql"
    path.write_text("CREATE TABLE example (id INT);\n", encoding="utf-8")

    first = calculate_sha256(path)
    second = calculate_sha256(path)

    assert first == second
    assert len(first) == 64
