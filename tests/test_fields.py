# test_fields.py
# qskos QGIS Plugin - unit tests for utils/fields.py
# Covers the lenient annotation value reader and annotation field detection.

from qskos.utils.fields import (
    parse_field_value,
    find_annotation_field_names,
)


class TestParseFieldValue:
    def test_none(self):
        assert parse_field_value(None) == []

    def test_empty_string(self):
        assert parse_field_value("") == []

    def test_canonical_json(self):
        assert parse_field_value('["http://a","http://b"]') == [
            "http://a", "http://b"
        ]

    def test_json_empty_array(self):
        assert parse_field_value("[]") == []

    def test_list_input(self):
        assert parse_field_value(["http://a", "http://b"]) == [
            "http://a", "http://b"
        ]

    def test_tuple_input(self):
        assert parse_field_value(("http://a", "http://b")) == [
            "http://a", "http://b"
        ]

    def test_legacy_postgres_array(self):
        assert parse_field_value("{http://a,http://b}") == [
            "http://a", "http://b"
        ]

    def test_legacy_pipe_separated(self):
        assert parse_field_value("http://a|http://b") == [
            "http://a", "http://b"
        ]

    def test_single_value(self):
        assert parse_field_value("http://a") == ["http://a"]

    def test_invalid_json_falls_back_to_single(self):
        # '[not valid' is not JSON -> treated as a bare single value
        assert parse_field_value("[not valid") == ["[not valid"]

    def test_quoted_postgres_array_from_text_field_widget(self):
        # What QGIS's ValueRelation widget writes into a *text* field
        # (annotation fields created by the 2026-10 refactor builds).
        assert parse_field_value('{"http://a","http://b"}') == [
            "http://a", "http://b",
        ]


class TestFindAnnotationFieldNames:
    def test_returns_known_concepts(self):
        fields = ["fid", "geom", "http://a", "http://b", "some_col"]
        labels = {"http://a": "A", "http://b": "B"}
        assert find_annotation_field_names(fields, labels) == [
            "http://a", "http://b"
        ]

    def test_no_matches(self):
        assert find_annotation_field_names(["fid", "geom"], {"http://a": "A"}) == []

    def test_empty(self):
        assert find_annotation_field_names([], {}) == []

    def test_excludes_non_concept_fields(self):
        fields = ["fid", "name", "http://x"]
        assert find_annotation_field_names(fields, {"http://x": "X"}) == [
            "http://x"
        ]
