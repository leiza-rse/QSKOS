# test_fields.py
# qskos QGIS Plugin - unit tests for utils/fields.py
# Covers the canonical JSON encode/decode plus the lenient legacy reader.

import json

from utils.fields import (
    encode_annotation_values,
    parse_field_value,
    find_annotation_field_names,
)


class TestEncodeAnnotationValues:
    def test_empty(self):
        assert encode_annotation_values([]) == "[]"

    def test_none(self):
        assert encode_annotation_values(None) == "[]"

    def test_uris(self):
        out = encode_annotation_values(["http://a", "http://b"])
        assert json.loads(out) == ["http://a", "http://b"]

    def test_strips_and_skips_blank(self):
        out = encode_annotation_values([" http://a ", "", "http://b"])
        assert json.loads(out) == ["http://a", "http://b"]

    def test_unicode_preserved(self):
        out = encode_annotation_values(["http://x/Ä"])
        assert "Ä" in out


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

    def test_roundtrip(self):
        uris = ["http://a", "http://b"]
        assert parse_field_value(encode_annotation_values(uris)) == uris


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
